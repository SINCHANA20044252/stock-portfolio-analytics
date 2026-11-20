import { useState } from 'react'
import { api } from '../api'
import { useToast } from '../context/AppContext'
import { todayISO } from '../lib/format'
import SymbolSearch from './SymbolSearch'
import { Modal } from './ui'

export const SECTORS = ['IT', 'Banking', 'Finance', 'Energy', 'Pharma', 'Auto', 'FMCG', 'Consumer', 'Infrastructure', 'Materials', 'Telecom', 'Index Fund', 'Gold', 'Other']

// Used for both adding (txn = null) and editing an existing transaction.
export default function TransactionForm({ txn, sectorOf = {}, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState(txn ? {
    symbol: txn.symbol, company_name: txn.company_name || '', sector: sectorOf[txn.symbol] || 'Other', type: txn.type,
    quantity: txn.quantity, price: txn.price, fees: txn.fees, date: txn.date, note: txn.note || '',
  } : { symbol: '', company_name: '', sector: 'Other', type: 'BUY', quantity: '', price: '', fees: 0, date: todayISO(), note: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    const body = { ...f, quantity: Number(f.quantity), price: Number(f.price), fees: Number(f.fees || 0), company_name: f.company_name || null, note: f.note || null }
    try {
      if (txn) await api.updateTransaction(txn.id, body); else await api.addTransaction(body)
      toast.success(txn ? 'Transaction updated' : `${f.type === 'BUY' ? 'Buy' : 'Sell'} recorded`)
      onSaved()
    } catch (err) { setError(err.message) }   // e.g. 409 "Cannot sell 5 INFY: only 3 held"
    finally { setBusy(false) }
  }

  return (
    <Modal title={txn ? 'Edit transaction' : 'Add transaction'} onClose={onClose} wide>
      <form onSubmit={submit} className="form-grid">
        {!txn && <div className="span2"><SymbolSearch onPick={(r) => setF({ ...f, symbol: r.symbol, company_name: r.name || '', sector: r.sector || f.sector })} /></div>}
        <label>Type
          <select value={f.type} onChange={set('type')}><option>BUY</option><option>SELL</option></select>
        </label>
        <label>Symbol<input value={f.symbol} onChange={set('symbol')} placeholder="INFY.NS" required maxLength={20} /></label>
        <label>Company<input value={f.company_name} onChange={set('company_name')} maxLength={120} /></label>
        <label>Sector<select value={f.sector} onChange={set('sector')}>{SECTORS.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label>Quantity<input type="number" step="any" min="0" value={f.quantity} onChange={set('quantity')} required /></label>
        <label>Price per share (₹)<input type="number" step="any" min="0" value={f.price} onChange={set('price')} required /></label>
        <label>Brokerage / charges (₹)<input type="number" step="any" min="0" value={f.fees} onChange={set('fees')} /></label>
        <label>Date<input type="date" max={todayISO()} value={f.date} onChange={set('date')} required /></label>
        <label className="span2">Note<input value={f.note} onChange={set('note')} maxLength={255} /></label>
        {error && <div className="errorbox span2" role="alert">{error}</div>}
        <div className="row end span2">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  )
}
