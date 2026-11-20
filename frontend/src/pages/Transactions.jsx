import { useState } from 'react'
import { api } from '../api'
import TransactionForm from '../components/TransactionForm'
import { Card, ConfirmDialog, EmptyState, ErrorState, PageSkeleton, useAsync } from '../components/ui'
import { useToast } from '../context/AppContext'
import { inr, shortDate, tone } from '../lib/format'

const PAGE = 25

export default function Transactions({ changed }) {
  const toast = useToast()
  const [filters, setFilters] = useState({ symbol: '', type: '', date_from: '', date_to: '' })
  const [offset, setOffset] = useState(0)
  const [form, setForm] = useState(null)       // null | 'new' | transaction being edited
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)
  const { data, error, loading, reload } = useAsync(() => api.transactions({ ...filters, limit: PAGE, offset }), [filters, offset])

  const setF = (k) => (e) => { setOffset(0); setFilters({ ...filters, [k]: e.target.value }) }
  const refresh = () => { reload(); changed?.() }

  async function confirmDelete() {
    setBusy(true)
    try { await api.deleteTransaction(deleting.id); toast.success('Transaction deleted'); setDeleting(null); refresh() }
    catch (e) { toast.error(e.message); setDeleting(null) }   // 409 if later sells would lose their shares
    finally { setBusy(false) }
  }

  return (
    <>
      <Card title="Filters" actions={<button className="btn primary" onClick={() => setForm('new')}>+ Add transaction</button>}>
        <div className="filters">
          <label>Stock<input value={filters.symbol} onChange={setF('symbol')} placeholder="INFY.NS" /></label>
          <label>Type<select value={filters.type} onChange={setF('type')}><option value="">All</option><option>BUY</option><option>SELL</option></select></label>
          <label>From<input type="date" value={filters.date_from} onChange={setF('date_from')} /></label>
          <label>To<input type="date" value={filters.date_to} onChange={setF('date_to')} /></label>
          <button className="btn" onClick={() => { setOffset(0); setFilters({ symbol: '', type: '', date_from: '', date_to: '' }) }}>Clear</button>
        </div>
      </Card>
      <Card title="History">
        {loading && !data ? <PageSkeleton /> : error ? <ErrorState message={error} onRetry={reload} /> :
          data.items.length === 0 ? <EmptyState title="No transactions found">Change the filters, add a transaction, or import a file.</EmptyState> : (
            <>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Date</th><th>Stock</th><th>Type</th><th className="num">Qty</th><th className="num">Price</th><th className="num">Charges</th><th className="num">Realized P&L</th><th /></tr></thead>
                  <tbody>
                    {data.items.map((t) => (
                      <tr key={t.id}>
                        <td>{shortDate(t.date)}</td>
                        <td><b>{t.symbol}</b><div className="muted small-text">{t.company_name || ''}{t.source !== 'manual' ? ` · ${t.source}` : ''}</div></td>
                        <td><span className={`chip ${t.type === 'BUY' ? 'buy' : 'sell'}`}>{t.type}</span></td>
                        <td className="num">{t.quantity}</td>
                        <td className="num">{inr(t.price, 2)}</td>
                        <td className="num">{inr(t.fees, 2)}</td>
                        <td className={`num ${tone(t.realized_pnl)}`}>{t.realized_pnl == null ? '—' : inr(t.realized_pnl, 2)}</td>
                        <td className="actions"><button className="link" onClick={() => setForm(t)}>Edit</button><button className="link bad" onClick={() => setDeleting(t)}>Delete</button></td>
                      </tr>))}
                  </tbody>
                </table>
              </div>
              <div className="row between" style={{ marginTop: 12 }}>
                <span className="muted small-text">Showing {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
                <div className="row">
                  <button className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                  <button className="btn small" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
                </div>
              </div>
            </>)}
      </Card>
      {form && <TransactionForm txn={form === 'new' ? null : form} onClose={() => setForm(null)} onSaved={() => { setForm(null); refresh() }} />}
      {deleting && <ConfirmDialog title="Delete this transaction?" busy={busy} onCancel={() => setDeleting(null)} onConfirm={confirmDelete}
        message={`${deleting.type} ${deleting.quantity} ${deleting.symbol} on ${shortDate(deleting.date)}. This changes your holdings and returns. It cannot be undone.`} />}
    </>
  )
}
