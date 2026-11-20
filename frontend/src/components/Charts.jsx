// Shared chart pieces. Palette is restrained and colour-blind friendly; colour never carries meaning alone.
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { compact, inr, pct } from '../lib/format'

export const COLORS = ['#3b5bdb', '#0ca678', '#f59f00', '#d6336c', '#7048e8', '#1098ad', '#82c91e', '#868e96']
export const GOOD = '#0ca678'
export const BAD = '#e03131'
export const AXIS = { tickLine: false, axisLine: false, fontSize: 12, stroke: 'var(--muted)' }

export function Frame({ height = 280, children }) {
  return <div className="chart" style={{ height }}><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div>
}

export const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, color: 'var(--text)', fontSize: 13 }

export function Donut({ data, nameKey, valueKey = 'value', height = 260 }) {
  const total = data.reduce((s, d) => s + d[valueKey], 0)
  return (
    <div className="donut-wrap">
      <Frame height={height}>
        <PieChart>
          <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius="58%" outerRadius="88%" paddingAngle={2} stroke="none">
            {data.map((d, i) => <Cell key={d[nameKey]} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} formatter={(v, n) => [`${inr(v)} (${total ? ((v / total) * 100).toFixed(1) : 0}%)`, n]} />
        </PieChart>
      </Frame>
      <ul className="legend">
        {data.map((d, i) => (
          <li key={d[nameKey]}><span className="dot" style={{ background: COLORS[i % COLORS.length] }} /><span>{d[nameKey]}</span><b>{total ? ((d[valueKey] / total) * 100).toFixed(1) : 0}%</b></li>
        ))}
      </ul>
    </div>
  )
}

// Bars coloured green for gains and red for losses (also differ in direction, so not colour-only).
export function ReturnBars({ data, xKey, yKey = 'return_pct', height = 240 }) {
  return (
    <Frame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis dataKey={xKey} {...AXIS} minTickGap={16} />
        <YAxis {...AXIS} tickFormatter={(v) => v + '%'} width={48} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v) => [pct(v, 2, true), 'Return']} cursor={{ fill: 'var(--line)', opacity: 0.4 }} />
        <Bar dataKey={yKey} radius={[3, 3, 0, 0]}>{data.map((d, i) => <Cell key={i} fill={d[yKey] >= 0 ? GOOD : BAD} />)}</Bar>
      </BarChart>
    </Frame>
  )
}

export function MultiLine({ data, xKey, lines, height = 280, yFormat = compact, dashedLast }) {
  return (
    <Frame height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis dataKey={xKey} {...AXIS} minTickGap={40} />
        <YAxis {...AXIS} tickFormatter={yFormat} width={56} domain={['auto', 'auto']} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v, n) => [typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : v, n]} />
        <Legend />
        {lines.map((l, i) => <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color || COLORS[i]} strokeWidth={2.2} dot={false} strokeDasharray={l.dash} isAnimationActive={false} connectNulls />)}
      </LineChart>
    </Frame>
  )
}
