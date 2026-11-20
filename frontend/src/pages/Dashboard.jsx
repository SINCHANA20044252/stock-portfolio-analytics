import { Area, AreaChart, CartesianGrid, Line, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { AXIS, COLORS, Donut, Frame, MultiLine, ReturnBars, tooltipStyle } from '../components/Charts'
import RefreshBar from '../components/RefreshBar'
import { Card, EmptyState, ErrorState, Notes, PageSkeleton, PeriodFilter, Stat, useAsync, usePersistentState } from '../components/ui'
import { compact, inr, pct, shortDate, tone } from '../lib/format'
import { downsample } from '../lib/periods'

export default function Dashboard({ go }) {
  const [period, setPeriod] = usePersistentState('period', 'ALL')
  const s = useAsync(() => api.summary(), [])
  const p = useAsync(() => api.performance(period), [period])

  if (s.loading && !s.data) return <PageSkeleton />
  if (s.error) return <ErrorState message={s.error} onRetry={s.reload} />
  const d = s.data
  if (!d.holdings.length && !d.closed.length) {
    return <EmptyState title="No transactions yet" action={<button className="btn primary" onClick={() => go('transactions')}>Add your first transaction</button>}>
      Record a buy, or import a CSV/Excel file, to see your value, returns and risk.</EmptyState>
  }
  const t = d.totals
  const perf = p.data
  const series = perf ? downsample(perf.series).map((r) => ({ ...r, label: shortDate(r.date), valueEst: r.estimated ? r.value : null })) : []
  const reload = () => { s.reload(); p.reload() }

  return (
    <>
      <RefreshBar asOf={d.prices_as_of} onRefreshed={reload} />
      {d.missing_prices.length > 0 && <div className="banner warn">No price yet for {d.missing_prices.join(', ')}. They are left out of the totals. Refresh prices or set one on the Holdings page.</div>}
      <div className="kpis">
        <Stat label="Portfolio value" value={inr(t.market_value)} sub={`${t.holdings_count} holding(s)`} />
        <Stat label="Total investment" value={inr(t.total_invested)} sub={`Still invested: ${inr(t.open_cost)}`} />
        <Stat label="Total profit / loss" value={inr(t.total_pnl)} tone={tone(t.total_pnl)} sub={`Unrealized ${inr(t.unrealized_pnl)} · Realized ${inr(t.realized_pnl)}`} />
        <Stat label="Overall return" value={pct(t.overall_return_pct, 2, true)} tone={tone(t.overall_return_pct)} sub="On everything you bought" />
        <Stat label="Best performer" value={d.best ? d.best.symbol : '—'} tone="good" sub={d.best ? pct(d.best.pct, 1, true) : 'n/a'} />
        <Stat label="Worst performer" value={d.worst ? d.worst.symbol : '—'} tone="bad" sub={d.worst ? pct(d.worst.pct, 1, true) : 'n/a'} />
      </div>

      <div className="row between wrap" style={{ margin: '8px 0 12px' }}>
        <h2 className="section">History</h2>
        <PeriodFilter value={period} onChange={setPeriod} />
      </div>
      {p.error && <ErrorState message={p.error} onRetry={p.reload} />}
      {perf && !perf.has_data && <EmptyState title="No price history yet">History is rebuilt from your transactions and stored daily prices. Use “Refresh prices” to load them. {perf.notes[0]}</EmptyState>}
      {perf?.has_data && (
        <>
          <div className="grid2">
            <Card title="Portfolio value over time" subtitle="Reconstructed from your trades and daily closing prices. Dashed = carried-forward price (estimate).">
              <Frame>
                <AreaChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <defs><linearGradient id="vfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={COLORS[0]} stopOpacity={0.3} /><stop offset="100%" stopColor={COLORS[0]} stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid vertical={false} stroke="var(--line)" />
                  <XAxis dataKey="label" {...AXIS} minTickGap={40} />
                  <YAxis {...AXIS} tickFormatter={compact} width={56} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v, n) => [inr(v), n]} />
                  <Area type="monotone" dataKey="value" name="Value" stroke={COLORS[0]} strokeWidth={2.2} fill="url(#vfill)" isAnimationActive={false} />
                  <Line type="monotone" dataKey="valueEst" name="Estimated day" stroke="#f59f00" strokeDasharray="4 3" dot={{ r: 2 }} isAnimationActive={false} />
                </AreaChart>
              </Frame>
            </Card>
            <Card title="Investment vs current value" subtitle="Cost of what you hold vs what it is worth.">
              <MultiLine data={series} xKey="label" lines={[{ key: 'invested', name: 'Invested', color: '#868e96' }, { key: 'value', name: 'Value', color: COLORS[0] }]} yFormat={compact} />
            </Card>
          </div>
          <div className="grid2">
            <Card title="Monthly returns" subtitle="Time-weighted, so deposits do not look like gains.">
              {perf.monthly.length ? <ReturnBars data={perf.monthly} xKey="period" /> : <p className="muted">Not enough history.</p>}
            </Card>
            <Card title="Portfolio vs benchmark" subtitle={`Both rebased to 100. Benchmark: ${perf.comparison.benchmark_symbol}`}>
              {perf.comparison.available
                ? <MultiLine data={downsample(perf.comparison.points).map((x) => ({ ...x, label: shortDate(x.date) }))} xKey="label" yFormat={(v) => Math.round(v)} lines={[{ key: 'portfolio', name: 'Portfolio' }, { key: 'benchmark', name: 'Benchmark', color: '#868e96', dash: '5 4' }]} />
                : <p className="muted">{perf.comparison.reason}</p>}
            </Card>
          </div>
          <Notes items={perf.notes} />
        </>
      )}

      <h2 className="section">Allocation and distribution</h2>
      <div className="grid2">
        <Card title="Sector allocation">{d.sectors.length ? <Donut data={d.sectors} nameKey="sector" /> : <p className="muted">No priced holdings.</p>}</Card>
        <Card title="Stock allocation">{d.stocks.length ? <Donut data={d.stocks} nameKey="symbol" /> : <p className="muted">No priced holdings.</p>}</Card>
      </div>
      <Card title="Profit / loss distribution" subtitle="How many holdings fall in each unrealized return range.">
        <ReturnBars data={d.pnl_distribution.map((b) => ({ ...b, return_pct: b.count }))} xKey="bucket" height={200} />
        <p className="muted small-text">Bar height = number of holdings. Hover for the count.</p>
      </Card>
    </>
  )
}
