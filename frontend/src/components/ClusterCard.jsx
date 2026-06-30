import { useState } from 'react'
import {
  Newspaper, TrendingUp, FileText, Briefcase,
  BookOpen, Activity,
} from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const FRONTEND_DOMAIN_GROUPS = {
  tech:       new Set(['news', 'arxiv', 'jobs', 'sec']),
  finance:    new Set(['stock', 'sec']),
  monitoring: new Set(['watcher']),
}

const TIER_STYLES = {
  breaking: {
    border: 'border-red-500/60',
    badge:  'bg-red-500/20 text-red-300 border border-red-500/40',
    bar:    'bg-red-400',
    glow:   'shadow-[0_0_20px_rgba(239,68,68,0.15)]',
  },
  emerging: {
    border: 'border-amber-500/50',
    badge:  'bg-amber-500/20 text-amber-300 border border-amber-500/40',
    bar:    'bg-amber-400',
    glow:   'shadow-[0_0_12px_rgba(245,158,11,0.1)]',
  },
  watch: {
    border: 'border-white/10',
    badge:  'bg-white/10 text-zinc-400 border border-white/10',
    bar:    'bg-zinc-500',
    glow:   '',
  },
}

// Thesis clusters: leading signals only, no news confirmation yet
const THESIS_STYLES = {
  border: 'border-violet-500/30 border-dashed',
  badge:  'bg-violet-500/10 text-violet-300 border border-violet-500/25',
  bar:    'bg-violet-400',
  glow:   'shadow-[0_0_18px_rgba(139,92,246,0.10)]',
}

const SOURCE_ICONS = {
  news:    Newspaper,
  stock:   TrendingUp,
  sec:     FileText,
  jobs:    Briefcase,
  arxiv:   BookOpen,
  watcher: Activity,
}

// Human-readable signal diversity labels
const SIGNAL_TYPE_LABELS = {
  stock:   'price',
  jobs:    'hiring',
  news:    'news',
  sec:     'SEC',
  arxiv:   'research',
  watcher: 'monitor',
}

function SourceTag({ type }) {
  const Icon = SOURCE_ICONS[type] ?? Newspaper
  return <Icon size={11} className="shrink-0 text-zinc-600" />
}

// Fallback for entities not in backend ENTITY_ALIASES (crypto, delisted, etc.)
const ENTITY_TO_TICKER_FALLBACK = {
  'Bitcoin': 'BTC',
  'Ethereum': 'ETH',
  'Solana': 'SOL',
  'eBay': 'EBAY',
}

function earningsLabel(dateStr) {
  if (!dateStr) return null
  const d = new Date(dateStr)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((d - today) / 86400000)
  if (days === 0) return 'Earnings today'
  if (days === 1) return 'Earnings tomorrow'
  if (days > 1 && days <= 3) return `Earnings in ${days}d`
  if (days === -1) return 'Reported yesterday'
  if (days < 0 && days >= -3) return `Reported ${-days}d ago`
  return null
}

function mixSourceLabel(signals, signalPhase, leadingSources, confirmingSources) {
  if (signalPhase === 'thesis') {
    const leadingLabels = [...new Set((leadingSources ?? []).map(t => SIGNAL_TYPE_LABELS[t] ?? t))]
    return leadingLabels.length > 0 ? `↑ ${leadingLabels.join(' · ')}` : '↑ leading'
  }
  if (signalPhase === 'confirming') {
    const leadingLabels = [...new Set((leadingSources ?? []).map(t => SIGNAL_TYPE_LABELS[t] ?? t))]
    const confirmLabels = [...new Set((confirmingSources ?? []).map(t => SIGNAL_TYPE_LABELS[t] ?? t))]
    return `↑ ${leadingLabels.join(' · ')} · ${confirmLabels.join(' · ')}`
  }
  // Dedupe by human label so "1 stock · 2 news" becomes "price · news"
  const labelSet = new Set(
    signals.map(s => SIGNAL_TYPE_LABELS[s.source_type] ?? s.source_type)
  )
  return [...labelSet].join(' · ')
}

function thesisAge(ts) {
  if (!ts) return null
  const diff = (Date.now() - new Date(ts).getTime()) / 1000
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return `${Math.floor(diff / 86400)}d`
}

function timeAgo(ts) {
  const normalized = /[Z+]/.test(ts) ? ts : ts + 'Z'
  const diff = (Date.now() - new Date(normalized).getTime()) / 1000
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function PriceBadge({ ticker, data }) {
  const up = data.pct_change >= 0
  const earnings = earningsLabel(data.next_earnings)
  return (
    <a
      href={`https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-baseline gap-1.5 text-xs font-mono"
      onClick={e => e.stopPropagation()}
    >
      <span className="text-zinc-500">{ticker}</span>
      <span className="text-zinc-300">
        {data.price < 1000 ? `$${data.price.toFixed(2)}` : `$${data.price.toFixed(0)}`}
      </span>
      <span className={up ? 'text-emerald-400' : 'text-red-400'}>
        {up ? '+' : ''}{data.pct_change.toFixed(1)}%
      </span>
      {earnings && <span className="text-amber-400/80 font-sans">{earnings}</span>}
    </a>
  )
}

function DiffPreview({ text }) {
  const [open, setOpen] = useState(false)
  const lines = text.split('\n').filter(l => l.trim())
  const removed = lines.filter(l => l.startsWith('−') || l.startsWith('-'))
  const added   = lines.filter(l => l.startsWith('+'))

  // Build a compact one-liner: show first removed → first added
  const summary = (() => {
    const r = removed[0]?.replace(/^[−-]\s*/, '').trim() ?? ''
    const a = added[0]?.replace(/^\+\s*/, '').trim() ?? ''
    if (r && a) return `− ${r.slice(0, 60)}${r.length > 60 ? '…' : ''}`
    return (r || a).slice(0, 80)
  })()

  return (
    <div className="mt-1">
      <button
        onClick={e => { e.preventDefault(); e.stopPropagation(); setOpen(v => !v) }}
        className="text-[11px] text-zinc-600 hover:text-zinc-400 font-mono transition-colors text-left"
      >
        {open ? '▾' : '▸'} {summary}
      </button>
      {open && (
        <pre className="mt-1 text-[11px] text-zinc-500 font-mono whitespace-pre-wrap leading-relaxed">
          {text}
        </pre>
      )}
    </div>
  )
}

export function ClusterCard({ cluster, prices = {}, entityToTicker = {}, maxScore = 60 }) {
  const isThesis = cluster.signal_phase === 'thesis'
  const thesisConfirmed = !isThesis
    && cluster.thesis_entered_at
    && cluster.signal_phase !== 'event'
  const thesisAgeLabel = thesisConfirmed ? thesisAge(cluster.thesis_entered_at) : null
  const styles = isThesis ? THESIS_STYLES : (TIER_STYLES[cluster.tier] || TIER_STYLES.watch)
  const momentumDisplay = Number.isFinite(cluster.momentum)
    ? Math.min(cluster.momentum, 99)
    : 0
  const hasMomentum = momentumDisplay >= 2
  const [summary, setSummary] = useState(null)
  const [loadingSummary, setLoadingSummary] = useState(false)

  const signalSources = new Set(cluster.signals.map(s => s.source_type))
  const domainsHit = Object.entries(FRONTEND_DOMAIN_GROUPS)
    .filter(([, types]) => [...types].some(t => signalSources.has(t)))
    .map(([d]) => d)
  const isCrossDomain = domainsHit.length >= 2
  const narrative = cluster.narrative ?? null

  const sourceLabel = mixSourceLabel(
    cluster.signals,
    cluster.signal_phase, cluster.leading_sources, cluster.confirming_sources
  )

  const resolvedEntityToTicker = { ...ENTITY_TO_TICKER_FALLBACK, ...entityToTicker }
  const priceEntries = cluster.entities
    .map(e => {
      const ticker = resolvedEntityToTicker[e] ?? (prices[e] ? e : null)
      return { ticker, data: ticker ? prices[ticker] : null }
    })
    .filter(x => x.ticker && x.data)

  async function fetchSummary() {
    if (summary) { setSummary(null); return }
    // Demo mode: the snapshot carries a pre-written summary, so no backend call.
    if (cluster.demo_summary) { setSummary(cluster.demo_summary); return }
    setLoadingSummary(true)
    try {
      const res = await fetch(`${API_URL}/api/clusters/${cluster.id}/summary`)
      const data = await res.json()
      setSummary(data.summary)
    } catch {
      setSummary('Failed to load summary.')
    } finally {
      setLoadingSummary(false)
    }
  }

  return (
    <div className={`rounded-xl border ${styles.border} ${styles.glow} bg-white/[0.03] p-3 mb-2 ${cluster.stale ? 'opacity-50' : ''}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="flex flex-wrap gap-1 items-center">
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full uppercase tracking-wide ${styles.badge}`}>
            {isThesis ? 'forming' : cluster.tier}
          </span>
          {hasMomentum && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/5 text-zinc-400 border border-white/10">
              ↑ {momentumDisplay.toFixed(1)}×
            </span>
          )}
          {thesisAgeLabel && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              ↑ thesis {thesisAgeLabel}
            </span>
          )}
          {isCrossDomain && cluster.tier === 'breaking' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20">
              {domainsHit.join(' · ')}
            </span>
          )}
          {narrative && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/8 text-zinc-300 border border-white/15 font-normal">
              {narrative}
            </span>
          )}
          {cluster.dominant_layer && cluster.entities.length > 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-zinc-500 border border-white/8 font-normal">
              {cluster.dominant_layer.replace(/_/g, ' ')}
            </span>
          )}
          <span className="text-xs font-semibold text-white">
            {cluster.entities.join(', ')}
          </span>
        </div>
        <span className="text-[10px] text-zinc-600 shrink-0">{sourceLabel}</span>
      </div>

      {/* Price badges */}
      {priceEntries.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 pt-0.5">
          {priceEntries.map(({ ticker, data }) => (
            <PriceBadge key={ticker} ticker={ticker} data={data} />
          ))}
        </div>
      )}

      {/* Signals — cap at 4 */}
      {(() => {
        const capped = cluster.signals.slice(0, 4)
        const extra  = cluster.signals.length - capped.length
        return (
          <div className="space-y-1 mt-1.5">
            {capped.map((sig, i) => {
              const stockTicker = sig.source_type === 'stock'
                ? (sig.entities ?? []).map(e => resolvedEntityToTicker[e] ?? (prices[e] ? e : null)).find(t => t && prices[t])
                : null
              const stockData = stockTicker ? prices[stockTicker] : null

              let displayTitle = sig.title
              if (stockData) {
                const vr = stockData.volume_ratio
                const volLabel = vr >= 2.0
                  ? `${vr.toFixed(1)}× avg volume`
                  : vr >= 1.5
                  ? `elevated volume (${vr.toFixed(1)}×)`
                  : 'normal volume'
                displayTitle = `${stockTicker} — ${volLabel}`
              }

              return (
                <div key={i} className="flex gap-1.5 items-baseline">
                  <SourceTag type={sig.source_type} />
                  <div className="min-w-0 flex-1">
                    <span className="text-[10px] text-zinc-600 mr-1.5 tabular-nums">{timeAgo(sig.timestamp)}</span>
                    {sig.url ? (
                      <a
                        href={sig.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`text-xs leading-snug hover:text-white transition-colors line-clamp-1 ${stockData ? 'text-zinc-500' : 'text-zinc-300'}`}
                      >
                        {displayTitle}
                      </a>
                    ) : (
                      <span className="text-xs text-zinc-300 leading-snug line-clamp-1">{displayTitle}</span>
                    )}
                    {sig.diff_preview && <DiffPreview text={sig.diff_preview} />}
                  </div>
                </div>
              )
            })}
            {extra > 0 && (
              <p className="text-[10px] text-zinc-700 pl-4">+{extra} more</p>
            )}
          </div>
        )
      })()}

      {/* Score bar — width relative to section max so top card is always full-width */}
      <div className="mt-2 flex items-center gap-2">
        <div className="flex-1 h-px bg-white/5 rounded-full overflow-hidden">
          <div
            className={`h-full ${styles.bar} rounded-full transition-all`}
            style={{ width: `${Math.min((cluster.score / Math.max(maxScore, cluster.score)) * 100, 100)}%` }}
          />
        </div>
        <span className="text-[10px] text-zinc-700 tabular-nums">{cluster.score.toFixed(0)}</span>
        <button
          onClick={fetchSummary}
          disabled={loadingSummary}
          className="text-[10px] text-zinc-400 hover:text-white border border-white/10 hover:border-white/20 px-1.5 py-0.5 rounded transition-colors disabled:opacity-40 ml-1"
        >
          {loadingSummary ? '…' : summary ? 'hide' : 'explain'}
        </button>
      </div>

      {summary && (
        <p className="mt-3 text-xs text-zinc-400 leading-relaxed border-t border-white/5 pt-3">
          {summary}
        </p>
      )}
    </div>
  )
}
