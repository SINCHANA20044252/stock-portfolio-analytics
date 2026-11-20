import { useRef, useState } from 'react'
import { api, download } from '../api'
import { Card, ConfirmDialog } from '../components/ui'
import { useToast } from '../context/AppContext'
import { inr, shortDate } from '../lib/format'

const EXPORTS = [
  ['holdings.csv', 'Holdings (CSV)'], ['transactions.csv', 'Transactions (CSV)'], ['pnl.csv', 'Profit and loss (CSV)'],
  ['analytics.csv', 'Portfolio analytics (CSV)'], ['report.xlsx', 'Full Excel report (4+ sheets)'],
]

export default function DataPage({ changed }) {
  const toast = useToast()
  const input = useRef(null)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState(false)

  async function onFile(e) {
    const file = e.target.files[0]
    e.target.value = ''
    if (!file) return
    setError(''); setBusy(true); setPreview(null)
    try { setPreview(await api.previewImport(file)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function doImport() {
    setBusy(true)
    try {
      const s = preview.summary
      const r = await api.confirmImport(preview.import_id, s.errors > 0)
      toast.success(`Imported ${r.imported} transaction(s)`); setPreview(null); setConfirm(false); changed?.()
    } catch (err) { setError(err.message); setConfirm(false) } finally { setBusy(false) }
  }
  async function cancel() {
    try { await api.cancelImport(preview.import_id) } catch { /* expired is fine */ }
    setPreview(null); toast.info('Import cancelled. Nothing was saved.')
  }
  async function exportFile(path) {
    try { await download('/data/export/' + path, path) } catch (e) { toast.error(e.message) }
  }

  const s = preview?.summary
  return (
    <>
      <Card title="Import transactions" subtitle="CSV or Excel (.xlsx). Required columns: date, symbol, type (BUY/SELL), quantity, price. Optional: fees, company_name, sector.">
        <div className="row wrap">
          <input ref={input} type="file" accept=".csv,.xlsx" onChange={onFile} hidden />
          <button className="btn primary" onClick={() => input.current.click()} disabled={busy}>{busy && !preview ? 'Reading file…' : 'Choose file'}</button>
          <button className="btn" onClick={() => download('/data/template.csv', 'transactions-template.csv').catch((e) => toast.error(e.message))}>Download CSV template</button>
        </div>
        {error && <div className="errorbox" role="alert">{error}</div>}
      </Card>

      {preview && (
        <Card title={`Preview: ${preview.filename}`} subtitle="Nothing is saved until you confirm.">
          <div className="kpis small">
            <div className="stat card"><div className="stat-label">Valid</div><div className="stat-value good">{s.valid}</div></div>
            <div className="stat card"><div className="stat-label">Duplicates (skipped)</div><div className="stat-value">{s.duplicates}</div></div>
            <div className="stat card"><div className="stat-label">Errors (not imported)</div><div className={`stat-value ${s.errors ? 'bad' : ''}`}>{s.errors}</div></div>
          </div>
          <div className="table-wrap tall">
            <table>
              <thead><tr><th>Row</th><th>Status</th><th>Date</th><th>Symbol</th><th>Type</th><th className="num">Qty</th><th className="num">Price</th><th>Problems</th></tr></thead>
              <tbody>{preview.rows.map((r) => (
                <tr key={r.row} className={r.status}>
                  <td>{r.row}</td><td><span className={`chip ${r.status}`}>{r.status}</span></td>
                  <td>{r.data.date ? shortDate(r.data.date) : '—'}</td><td>{r.data.symbol || '—'}</td><td>{r.data.type || '—'}</td>
                  <td className="num">{r.data.quantity ?? '—'}</td><td className="num">{r.data.price == null ? '—' : inr(r.data.price, 2)}</td>
                  <td className="small-text">{r.errors.join('; ')}</td>
                </tr>))}</tbody>
            </table>
          </div>
          {s.errors > 0 && <p className="banner warn">{s.errors} row(s) have errors and will NOT be imported. Fix the file and upload again, or import only the {s.valid} valid row(s).</p>}
          <div className="row end">
            <button className="btn" onClick={cancel}>Cancel import</button>
            <button className="btn primary" disabled={!s.valid || busy} onClick={() => setConfirm(true)}>{s.errors ? `Import ${s.valid} valid row(s) only` : `Import ${s.valid} row(s)`}</button>
          </div>
        </Card>
      )}
      {confirm && <ConfirmDialog title="Import these transactions?" danger={false} confirmLabel="Import" busy={busy} onCancel={() => setConfirm(false)} onConfirm={doImport}
        message={`${s.valid} transaction(s) will be added to your history.${s.errors ? ` ${s.errors} invalid row(s) will be skipped.` : ''}`} />}

      <Card title="Export" subtitle="Downloads contain your own data only.">
        <div className="row wrap">{EXPORTS.map(([p, label]) => <button key={p} className="btn" onClick={() => exportFile(p)}>{label}</button>)}</div>
      </Card>
    </>
  )
}
