import { useState, useEffect, useCallback } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const POLL_INTERVAL = 5 * 60 * 1000
const CACHE_KEY = 'signal_v1'

function readCache() {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY)) } catch { return null }
}

function writeCache(clusters, prices) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ clusters, prices, savedAt: Date.now() })) } catch {}
}

export function useData() {
  const cached = readCache()
  const [clusters, setClusters] = useState(cached?.clusters ?? [])
  const [prices, setPrices] = useState(cached?.prices ?? {})
  const [entityToTicker, setEntityToTicker] = useState({})
  const [loading, setLoading] = useState(true)
  const [fromCache, setFromCache] = useState(!!cached)
  const [lastUpdated, setLastUpdated] = useState(cached ? new Date(cached.savedAt) : null)

  const fetchAll = useCallback(async () => {
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
      setLastUpdated(new Date())
      setFromCache(false)
      writeCache(newClusters, newPrices)
    } catch {
      // backend down — keep showing cached data silently
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchAll])

  return { clusters, prices, entityToTicker, loading, fromCache, lastUpdated, refresh: fetchAll }
}
