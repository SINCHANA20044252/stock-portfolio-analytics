import test from 'node:test'
import assert from 'node:assert/strict'
import { inr, pct, compact, tone, shortDate, timeAgo, todayISO } from './format.js'
import { sortRows, nextSort } from './sort.js'
import { buildQuery, errorMessage } from './query.js'
import { downsample, riskTone, PERIODS } from './periods.js'

test('inr uses Indian digit grouping and handles missing values', () => {
  assert.equal(inr(1234567.5, 2), '₹12,34,567.50')
  assert.equal(inr(-999), '-₹999')
  assert.equal(inr(null), '—')
  assert.equal(inr(100000), '₹1,00,000')
})

test('pct formats with optional sign', () => {
  assert.equal(pct(5), '5.00%')
  assert.equal(pct(5, 1, true), '+5.0%')
  assert.equal(pct(-2.345, 1, true), '-2.3%')
  assert.equal(pct(undefined), '—')
})

test('compact uses lakh/crore', () => {
  assert.equal(compact(15000000), '1.5Cr')
  assert.equal(compact(250000), '2.5L')
  assert.equal(compact(12000), '12K')
  assert.equal(compact(-250000), '-2.5L')
  assert.equal(compact(950), '950')
})

test('tone', () => {
  assert.equal(tone(3), 'good'); assert.equal(tone(-3), 'bad'); assert.equal(tone(0), ''); assert.equal(tone(null), '')
})

test('dates', () => {
  assert.equal(shortDate('2025-03-07'), '7 Mar 2025')
  assert.equal(shortDate(null), '—')
  assert.equal(todayISO(new Date(2025, 0, 5)), '2025-01-05')
  const now = Date.parse('2025-01-01T12:00:00Z')
  assert.equal(timeAgo('2025-01-01T11:55:00Z', now), '5 min ago')
  assert.equal(timeAgo('2025-01-01T09:00:00Z', now), '3 h ago')
  assert.equal(timeAgo(null), 'never')
})

test('sortRows puts nulls last in both directions and does not mutate', () => {
  const rows = [{ v: 2 }, { v: null }, { v: 1 }]
  assert.deepEqual(sortRows(rows, (r) => r.v, 1).map((r) => r.v), [1, 2, null])
  assert.deepEqual(sortRows(rows, (r) => r.v, -1).map((r) => r.v), [2, 1, null])
  assert.equal(rows[0].v, 2)
})

test('nextSort toggles direction on the same key', () => {
  assert.deepEqual(nextSort({ key: 'a', dir: 1 }, 'a'), { key: 'a', dir: -1 })
  assert.deepEqual(nextSort({ key: 'a', dir: -1 }, 'b'), { key: 'b', dir: 1 })
})

test('buildQuery skips empty values', () => {
  assert.equal(buildQuery({ a: 1, b: '', c: null, d: 'x y' }), '?a=1&d=x+y')
  assert.equal(buildQuery({}), '')
})

test('errorMessage reads FastAPI error shapes', () => {
  assert.equal(errorMessage({ detail: 'Nope' }), 'Nope')
  assert.equal(errorMessage({ detail: [{ loc: ['body', 'quantity'], msg: 'Input should be greater than 0' }] }), 'quantity: Input should be greater than 0')
  assert.equal(errorMessage({}, 'fallback'), 'fallback')
})

test('downsample keeps the last point and the cap', () => {
  const rows = Array.from({ length: 1000 }, (_, i) => i)
  const out = downsample(rows, 100)
  assert.ok(out.length <= 101 && out.at(-1) === 999)
  assert.equal(downsample([1, 2, 3], 100).length, 3)
})

test('risk tone and periods', () => {
  assert.equal(riskTone('Low'), 'good'); assert.equal(riskTone('High'), 'bad'); assert.equal(riskTone('x'), '')
  assert.deepEqual(PERIODS, ['1W', '1M', '3M', '6M', '1Y', 'ALL'])
})
