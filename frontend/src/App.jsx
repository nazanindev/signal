import { useData } from './hooks/useData'
import { ClusterCard } from './components/ClusterCard'
import './index.css'

function timeStr(date) {
  if (!date) return '—'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function App() {
  const { clusters, prices, entityToTicker, loading, fromCache, demo, lastUpdated, refresh } = useData()

  // Thesis: leading-only clusters — the gap before news catches up
  const thesis = clusters.filter(c => c.signal_phase === 'thesis')
  const confirmed = clusters.filter(c => c.signal_phase !== 'thesis')

  const breaking = confirmed.filter(c => c.tier === 'breaking')
  const emerging = confirmed.filter(c => c.tier === 'emerging')
  const watch    = confirmed.filter(c => c.tier === 'watch')

  return (
    <div
      className="max-w-lg mx-auto px-4 pb-24"
      style={{ paddingTop: 'calc(1.5rem + env(safe-area-inset-top))' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-white tracking-tight">Signal</h1>
            {demo && (
              <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-300/90 border border-amber-500/30">
                sample data
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-600">
            {demo
              ? 'demo — not live'
              : (loading && !lastUpdated ? 'Loading...' : fromCache ? `Cached ${timeStr(lastUpdated)}` : `Updated ${timeStr(lastUpdated)}`)}
            <span className="text-zinc-700"> · a calmer news feed</span>
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="w-8 h-8 rounded-full bg-zinc-800 border border-white/10 text-zinc-400 hover:text-white hover:bg-zinc-700 transition-all flex items-center justify-center disabled:opacity-40"
          aria-label="Refresh"
        >
          <span className={loading ? 'animate-spin inline-block' : ''}>↻</span>
        </button>
      </div>

      {loading && clusters.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <div className="w-6 h-6 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" />
          <p className="text-sm text-zinc-600">Fetching signals...</p>
        </div>
      )}

      {!loading && clusters.length === 0 && (
        <div className="text-center py-20">
          <p className="text-zinc-500 text-sm">No clusters surfaced yet.</p>
          <p className="text-zinc-700 text-xs mt-1">Check back in a few minutes.</p>
        </div>
      )}

      {thesis.length > 0 && (() => {
        const max = Math.max(...thesis.map(c => c.score))
        return (
          <Section title="Thesis" count={thesis.length}>
            {thesis.map(c => <ClusterCard key={c.id} cluster={c} prices={prices} entityToTicker={entityToTicker} maxScore={max} />)}
          </Section>
        )
      })()}

      {breaking.length > 0 && (() => {
        const max = Math.max(...breaking.map(c => c.score))
        return (
          <Section title="Breaking" count={breaking.length}>
            {breaking.map(c => <ClusterCard key={c.id} cluster={c} prices={prices} entityToTicker={entityToTicker} maxScore={max} />)}
          </Section>
        )
      })()}

      {emerging.length > 0 && (() => {
        const max = Math.max(...emerging.map(c => c.score))
        return (
          <Section title="Emerging" count={emerging.length}>
            {emerging.map(c => <ClusterCard key={c.id} cluster={c} prices={prices} entityToTicker={entityToTicker} maxScore={max} />)}
          </Section>
        )
      })()}

      {watch.length > 0 && (() => {
        const max = Math.max(...watch.map(c => c.score))
        return (
          <Section title="Watch" count={watch.length}>
            {watch.map(c => <ClusterCard key={c.id} cluster={c} prices={prices} entityToTicker={entityToTicker} maxScore={max} />)}
          </Section>
        )
      })()}
    </div>
  )
}

function Section({ title, count, children }) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <h2 className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest">{title}</h2>
        <span className="text-[10px] text-zinc-700">{count}</span>
        <div className="flex-1 h-px bg-white/5" />
      </div>
      {children}
    </div>
  )
}
