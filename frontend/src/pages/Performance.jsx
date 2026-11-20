import { useState } from 'react'
import { api } from '../api'
import { MultiLine, ReturnBars } from '../components/Charts'
import { Card, EmptyState, ErrorState, Notes, PageSkeleton, PeriodFilter, Stat, useAsync, usePersistentState } from '../components/ui'
import { pct, shortDate, tone } from '../lib/format'
import { downsample } from '../lib/periods'

const best = (b) => (b ? `${b.period} (${pct(b.return_pct, 2, true)})` : '—')

export default function Performance() {
  const [period, setPeriod] = usePersistentState('period', 'ALL')
  const [daily, setDaily] = useState(false)
  const { data, error, loading, reload } = useAsync(() => api.performance(period), [period])

  if (loading && !data) return <PageSkeleton />
  if (error) return <ErrorState message={error} onRetry={reload} />
  const s = data.summary
  return (
    <>
      <div className="row between wrap"><p className="muted small-text">{data.source}</p><PeriodFilter value={period} onChange={setPeriod} /></div>
      {!data.has_data ? (
        <EmptyState title="No performance data yet">Performance needs transactions plus stored daily prices. Use “Refresh prices” on the Dashboard or Holdings page.<Notes items={data.notes} /></EmptyState>
      ) : (
        <>
          <div className="kpis">
            <Stat label="Cumulative return (time-weighted)" value={pct(s.cumulative_return_pct, 2, true)} tone={tone(s.cumulative_return_pct)} sub={`${shortDate(s.start_date)} → ${shortDate(s.end_date)}`} />
            <Stat label="Portfolio growth" value={pct(s.portfolio_growth_pct, 2, true)} tone={tone(s.portfolio_growth_pct)} sub="Value vs cost of holdings" />
            <Stat label="Annualized return" value={s.annualized_return_pct == null ? 'n/a' : pct(s.annualized_return_pct, 2, true)} sub={s.annualized_note || 'Compound yearly rate'} />
            <Stat label="Best day" value={best(s.best_day)} tone="good" />
            <Stat label="Worst day" value={best(s.worst_day)} tone="bad" />
            <Stat label="Best / worst month" value={best(s.monthly.best)} sub={`Worst: ${best(s.monthly.worst)}`} />
          </div>
          <Card title="Cumulative return" subtitle="Time-weighted: buying or selling does not count as performance.">
            <MultiLine data={downsample(data.series).map((r) => ({ ...r, label: shortDate(r.date) }))} xKey="label" yFormat={(v) => v + '%'}
              lines={[{ key: 'cumulative_return_pct', name: 'Cumulative return %' }]} />
          </Card>
          <div className="grid2">
            <Card title="Weekly returns"><ReturnBars data={data.weekly.slice(-52)} xKey="period" /></Card>
            <Card title="Monthly returns"><ReturnBars data={data.monthly} xKey="period" /></Card>
          </div>
          <Card title="Daily returns" actions={<button className="btn small" onClick={() => setDaily(!daily)}>{daily ? 'Hide' : 'Show'}</button>}>
            {daily ? <ReturnBars data={data.series.filter((r) => r.daily_return_pct != null).slice(-250)} xKey="date" yKey="daily_return_pct" /> : <p className="muted small-text">Shows up to the last 250 trading days.</p>}
          </Card>
          {data.series.some((r) => r.estimated) && <p className="banner warn">Some days use the previous close (holiday or missing data). Those values are estimates.</p>}
          <Notes items={data.notes} />
        </>
      )}
    </>
  )
}
