import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { AXIS, COLORS, Frame, MultiLine, tooltipStyle } from '../components/Charts'
import { Card, ConfirmDialog, ErrorState, Stat, useAsync } from '../components/ui'
import { useToast } from '../context/AppContext'
import { compact, inr } from '../lib/format'

const DEFAULT = { target: 2000000, years: 10, monthly_sip: 10000, annual_return_pct: 10, starting_amount: '' }

function Planner() {
  const toast = useToast()
  const [form, setForm] = useState(DEFAULT)
  const [name, setName] = useState('')
  const [res, setRes] = useState(null)
  const [error, setError] = useState('')
  const goals = useAsync(() => api.goals(), [])
  const [del, setDel] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value === '' ? '' : Number(e.target.value) })

  // Recalculate 250 ms after the last change so dragging a slider updates live.
  useEffect(() => {
    if (!form.target || form.target < 1) return
    const t = setTimeout(() => {
      api.plan({ ...form, starting_amount: form.starting_amount === '' ? null : form.starting_amount }).then((r) => { setRes(r); setError('') }).catch((e) => setError(e.message))
    }, 250)
    return () => clearTimeout(t)
  }, [form])

  async function save() {
    try {
      await api.saveGoal({ name, target_amount: form.target, years: form.years, expected_return_pct: form.annual_return_pct, monthly_sip: form.monthly_sip, starting_amount: form.starting_amount === '' ? null : form.starting_amount })
      toast.success('Goal saved'); setName(''); goals.reload()
    } catch (e) { toast.error(e.message) }
  }
  const load = (g) => setForm({ target: g.target_amount, years: g.years, monthly_sip: g.monthly_sip, annual_return_pct: g.expected_return_pct, starting_amount: g.starting_amount ?? '' })

  return (
    <>
      <Card title="Set your goal" subtitle="Projections are estimates based on a constant assumed return. They are not guaranteed.">
        <div className="sliders">
          <label>Target amount (₹)<input type="number" min="1" value={form.target} onChange={set('target')} /></label>
          <label>Starting amount (₹), blank = your portfolio value<input type="number" min="0" value={form.starting_amount} onChange={set('starting_amount')} /></label>
          <label><span className="slider-head">Years <b>{form.years}</b></span><input type="range" min="1" max="40" value={form.years} onChange={set('years')} /></label>
          <label><span className="slider-head">Monthly SIP <b>{inr(form.monthly_sip)}</b></span><input type="range" min="0" max="200000" step="500" value={form.monthly_sip} onChange={set('monthly_sip')} /></label>
          <label><span className="slider-head">Expected return <b>{form.annual_return_pct}% a year</b></span><input type="range" min="0" max="20" step="0.5" value={form.annual_return_pct} onChange={set('annual_return_pct')} /></label>
        </div>
        {error && <div className="errorbox" role="alert">{error}</div>}
      </Card>

      {res && (
        <>
          <div className="kpis">
            <Stat label="Required monthly SIP" value={inr(res.required_monthly_sip)} sub="To hit the target at this return" />
            <Stat label="Total invested" value={inr(res.total_invested)} sub={`Starting ${inr(res.starting_value)}`} />
            <Stat label="Estimated returns" value={inr(res.estimated_returns)} tone="good" sub="Estimate, not guaranteed" />
            <Stat label="Projected final value" value={inr(res.projected_value)} tone={res.on_track ? 'good' : 'bad'} sub={res.on_track ? 'On track for the target' : `Short by ${inr(res.shortfall)}`} />
          </div>
          <Card title="Year-wise growth (estimate)">
            <Frame>
              <BarChart data={res.series} margin={{ top: 8, right: 12, left: 0, bottom: 16 }}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="year" {...AXIS} label={{ value: 'Years from now', position: 'insideBottom', offset: -8, fontSize: 12 }} />
                <YAxis {...AXIS} tickFormatter={compact} width={56} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v, n) => [inr(v), n]} labelFormatter={(y) => `Year ${y}`} />
                <ReferenceLine y={res.target} stroke="#e03131" strokeDasharray="5 5" label={{ value: 'Target', fill: '#e03131', fontSize: 12, position: 'insideTopLeft' }} />
                <Bar dataKey="invested" name="Invested" stackId="a" fill="#868e96" />
                <Bar dataKey="returns" name="Estimated returns" stackId="a" fill={COLORS[0]} radius={[3, 3, 0, 0]} />
              </BarChart>
            </Frame>
            <div className="table-wrap"><table><thead><tr><th>Year</th><th className="num">Invested</th><th className="num">Est. returns</th><th className="num">Value</th></tr></thead>
              <tbody>{res.series.map((r) => <tr key={r.year}><td>{r.year}</td><td className="num">{inr(r.invested)}</td><td className="num">{inr(r.returns)}</td><td className="num">{inr(r.value)}</td></tr>)}</tbody></table></div>
            <p className="muted small-text">{res.disclaimer}</p>
          </Card>
        </>
      )}

      <Card title="Saved goals">
        <div className="row wrap" style={{ marginBottom: 12 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name this plan (e.g. House down payment)" maxLength={80} />
          <button className="btn primary" disabled={!name.trim()} onClick={save}>Save current plan</button>
        </div>
        {goals.error ? <ErrorState message={goals.error} onRetry={goals.reload} /> : !goals.data?.length ? <p className="muted">No saved goals yet.</p> : (
          <ul className="list">{goals.data.map((g) => (
            <li key={g.id}><div><b>{g.name}</b><div className="muted small-text">{inr(g.target_amount)} in {g.years} yrs · SIP {inr(g.monthly_sip)} · {g.expected_return_pct}% · projected {inr(g.projection.projected_value)} ({g.projection.on_track ? 'on track' : `short ${inr(g.projection.shortfall)}`})</div></div>
              <div className="row"><button className="link" onClick={() => load(g)}>Load</button><button className="link bad" onClick={() => setDel(g)}>Delete</button></div></li>))}</ul>)}
      </Card>
      {del && <ConfirmDialog title="Delete goal?" message={`“${del.name}” will be removed.`} onCancel={() => setDel(null)}
        onConfirm={async () => { try { await api.deleteGoal(del.id); toast.success('Goal deleted'); goals.reload() } catch (e) { toast.error(e.message) } setDel(null) }} />}
    </>
  )
}

function Compare() {
  const [target, setTarget] = useState(2000000)
  const [rows, setRows] = useState([
    { name: 'Cautious', years: 10, annual_return_pct: 7, monthly_sip: '' },
    { name: 'Balanced', years: 10, annual_return_pct: 10, monthly_sip: '' },
    { name: 'Optimistic', years: 10, annual_return_pct: 12, monthly_sip: '' },
  ])
  const [res, setRes] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const upd = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)))

  async function run() {
    setBusy(true); setError('')
    try {
      setRes(await api.compare({ target, scenarios: rows.map((r) => ({ name: r.name || null, years: Number(r.years), annual_return_pct: Number(r.annual_return_pct), monthly_sip: r.monthly_sip === '' ? null : Number(r.monthly_sip) })) }))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const merged = res ? Array.from({ length: Math.max(...res.scenarios.map((s) => s.years)) }, (_, i) => Object.fromEntries([['year', i + 1], ...res.scenarios.map((s, j) => [`s${j}`, s.series[i]?.value ?? null])])) : []

  return (
    <Card title="Compare scenarios" subtitle="Leave SIP blank to solve the monthly amount needed for the target. All figures are estimates.">
      <label className="inline-label">Target (₹)<input type="number" min="1" value={target} onChange={(e) => setTarget(Number(e.target.value))} /></label>
      <div className="table-wrap"><table><thead><tr><th>Name</th><th>Years</th><th>Return %</th><th>Monthly SIP (₹)</th><th /></tr></thead><tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td><input value={r.name} onChange={(e) => upd(i, 'name', e.target.value)} maxLength={40} /></td>
            <td><input type="number" min="1" max="50" value={r.years} onChange={(e) => upd(i, 'years', e.target.value)} /></td>
            <td><input type="number" min="0" max="30" step="0.5" value={r.annual_return_pct} onChange={(e) => upd(i, 'annual_return_pct', e.target.value)} /></td>
            <td><input type="number" min="0" placeholder="solve" value={r.monthly_sip} onChange={(e) => upd(i, 'monthly_sip', e.target.value)} /></td>
            <td><button className="link bad" disabled={rows.length < 2} onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button></td>
          </tr>))}</tbody></table></div>
      <div className="row"><button className="btn" disabled={rows.length >= 6} onClick={() => setRows([...rows, { name: `Scenario ${rows.length + 1}`, years: 10, annual_return_pct: 8, monthly_sip: '' }])}>+ Add scenario</button>
        <button className="btn primary" onClick={run} disabled={busy}>{busy ? 'Calculating…' : 'Compare'}</button></div>
      {error && <div className="errorbox" role="alert">{error}</div>}
      {res && (
        <>
          <MultiLine data={merged} xKey="year" lines={res.scenarios.map((s, j) => ({ key: `s${j}`, name: s.name }))} />
          <div className="table-wrap"><table><thead><tr><th>Scenario</th><th className="num">Monthly SIP</th><th className="num">Invested</th><th className="num">Est. returns</th><th className="num">Final value</th></tr></thead>
            <tbody>{res.scenarios.map((s) => <tr key={s.name}><td>{s.name} <span className="muted small-text">({s.years} yrs, {s.annual_return_pct}%)</span></td><td className="num">{inr(s.monthly_sip)}{s.sip_was_solved ? ' (solved)' : ''}</td><td className="num">{inr(s.total_invested)}</td><td className="num">{inr(s.estimated_returns)}</td><td className="num">{inr(s.projected_value)}</td></tr>)}</tbody></table></div>
        </>)}
    </Card>
  )
}

export default function Goals() {
  return <><Planner /><Compare /></>
}
