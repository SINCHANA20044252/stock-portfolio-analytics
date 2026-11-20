import { api } from '../api'
import { Card, EmptyState, ErrorState, PageSkeleton, Stat, useAsync } from '../components/ui'
import { pct } from '../lib/format'
import { riskTone } from '../lib/periods'

function Bars({ weights, limit }) {
  const rows = Object.entries(weights).sort((a, b) => b[1] - a[1])
  return (
    <ul className="bars">
      {rows.map(([k, v]) => (
        <li key={k}><span>{k}</span>
          <div className="track"><div className={`fill ${v > limit ? 'over' : ''}`} style={{ width: `${Math.min(100, v)}%` }} /><i style={{ left: `${limit}%` }} title={`${limit}% limit`} /></div>
          <b>{pct(v, 1)}</b></li>))}
    </ul>
  )
}

export default function Risk() {
  const { data, error, loading, reload } = useAsync(() => api.risk(), [])
  if (loading && !data) return <PageSkeleton />
  if (error) return <ErrorState message={error} onRetry={reload} />
  const c = data.concentration
  if (!c.has_data) return <EmptyState title="Nothing to analyse yet">{data.warnings[0]}</EmptyState>
  const m = data.metrics
  return (
    <>
      <div className="kpis">
        <Stat label="Risk score (higher = riskier)" value={`${data.risk_score} / 100`} tone={riskTone(data.risk_category)} sub={`Category: ${data.risk_category}`} />
        <Stat label="Diversification score" value={`${data.diversification_score} / 100`} sub="Higher is more spread out" />
        <Stat label="HHI" value={c.hhi} sub={`≈ ${c.effective_holdings} equal holdings`} />
        <Stat label="Volatility (annualised)" value={m.volatility_pct == null ? 'n/a' : pct(m.volatility_pct, 1)} />
        <Stat label="Maximum drawdown" value={m.max_drawdown_pct == null ? 'n/a' : pct(m.max_drawdown_pct, 1)} sub={m.max_drawdown_peak ? `${m.max_drawdown_peak} → ${m.max_drawdown_trough}` : undefined} />
        <Stat label="Sharpe ratio" value={m.sharpe == null ? 'n/a' : m.sharpe} />
      </div>
      {m.notes.length > 0 && <ul className="notes">{m.notes.map((n) => <li key={n}>{n}</li>)}</ul>}

      {data.warnings.length > 0 && <div className="banner warn"><strong>Warnings</strong><ul>{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>}
      <Card title="Insights"><ul className="plain">{data.insights.map((i) => <li key={i}>{i}</li>)}</ul></Card>
      <div className="grid2">
        <Card title="Stock concentration" subtitle="Marker shows the 40% single-stock limit."><Bars weights={c.stock_weights} limit={40} /></Card>
        <Card title="Sector concentration" subtitle="Marker shows the 50% single-sector limit."><Bars weights={c.sector_weights} limit={50} /></Card>
      </div>
      <Card title="How each metric is calculated">
        <dl className="how">{data.methodology.map((x) => <div key={x.metric}><dt>{x.metric}</dt><dd>{x.how}</dd></div>)}</dl>
      </Card>
      <p className="banner">{data.disclaimer}</p>
    </>
  )
}
