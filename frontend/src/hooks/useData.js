import { useState, useEffect, useCallback } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
// Demo mode: serve the bundled sample snapshot instead of a live backend.
// Forced on when VITE_DEMO=true (the public demo build); otherwise used as a
// fallback when no backend is reachable.
const DEMO = import.meta.env.VITE_DEMO === 'true'
const POLL_INTERVAL = 5 * 60 * 1000
const CACHE_KEY = 'signal_v1'

function readCache() {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY)) } catch { return null }
}

function writeCache(clusters, prices) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ clusters, prices, savedAt: Date.now() })) } catch {}
}

// Turn the fixture's relative ages (_age_min / _thesis_age_min) into real
// timestamps at load time so the sample feed never looks stale.
function hydrateDemo(clusters) {
  const now = Date.now()
  const ago = (min) => new Date(now - (min ?? 60) * 60000).toISOString()
  return clusters.map(({ _thesis_age_min, ...c }) => ({
    ...c,
    thesis_entered_at: _thesis_age_min != null ? ago(_thesis_age_min) : (c.thesis_entered_at ?? null),
    signals: (c.signals ?? []).map(({ _age_min, ...s }) => ({ ...s, timestamp: ago(_age_min) })),
  }))
}

async function loadDemo() {
  const base = import.meta.env.BASE_URL || '/'
  const [feed, stocks] = await Promise.all([
    window.fetch(`${base}demo/feed.json`).then(r => r.json()),
    window.fetch(`${base}demo/stocks.json`).then(r => r.json()),
  ])
  return {
    clusters: hydrateDemo(feed.clusters || []),
    prices: stocks.prices || {},
    entityToTicker: stocks.entity_to_ticker || {},
  }
}

export function useData() {
  const cached = readCache()
  const [clusters, setClusters] = useState(cached?.clusters ?? [])
  const [prices, setPrices] = useState(cached?.prices ?? {})
  const [entityToTicker, setEntityToTicker] = useState({})
  const [loading, setLoading] = useState(true)
  const [fromCache, setFromCache] = useState(!!cached)
  const [demo, setDemo] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(cached ? new Date(cached.savedAt) : null)

  const applyDemo = useCallback(async () => {
    try {
      const d = await loadDemo()
      setClusters(d.clusters)
      setPrices(d.prices)
      setEntityToTicker(d.entityToTicker)
      setDemo(true)
      setFromCache(false)
      setLastUpdated(new Date())
    } catch {
      // demo data missing — leave whatever's on screen
    }
  }, [])

  const fetchAll = useCallback(async () => {
    if (DEMO) {
      await applyDemo()
      setLoading(false)
      return
    }
    try {
      const [feedRes, pricesRes] = await Promise.all([
        window.fetch(`${API_URL}/api/feed`),
        window.fetch(`${API_URL}/api/stocks`),
      ])
      if (!feedRes.ok || !pricesRes.ok) throw new Error(`HTTP ${feedRes.status}`)
      const [feedData, pricesData] = await Promise.all([feedRes.json(), pricesRes.json()])
      const newClusters = feedData.clusters || []
      const newPrices = pricesData.prices || {}
      // Backend is warming up after redeploy — don't overwrite cached data with empty response
      if (newClusters.length === 0 && readCache()?.clusters?.length > 0) return
      setClusters(newClusters)
      setPrices(newPrices)
      setEntityToTicker(pricesData.entity_to_ticker || {})
      setDemo(false)
      setLastUpdated(new Date())
      setFromCache(false)
      writeCache(newClusters, newPrices)
    } catch {
      // No backend reachable. Fall back to the bundled demo if we have nothing to show.
      if (!readCache()?.clusters?.length) await applyDemo()
    } finally {
      setLoading(false)
    }
  }, [applyDemo])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchAll])

  return { clusters, prices, entityToTicker, loading, fromCache, demo, lastUpdated, refresh: fetchAll }
}
