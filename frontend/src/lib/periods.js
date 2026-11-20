export const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
export const PERIOD_LABELS = { '1W': '1 week', '1M': '1 month', '3M': '3 months', '6M': '6 months', '1Y': '1 year', ALL: 'All time' }

// Thin a long series so charts stay fast: keep at most `max` points, always including the last one.
export function downsample(rows, max = 400) {
  if (rows.length <= max) return rows
  const step = Math.ceil(rows.length / max)
  const out = rows.filter((_, i) => i % step === 0)
  if (out[out.length - 1] !== rows[rows.length - 1]) out.push(rows[rows.length - 1])
  return out
}

// Colour for a diversification/risk number: lower risk score is better.
export function riskTone(category) {
  return { Low: 'good', Moderate: 'warn', High: 'bad' }[category] || ''
}
