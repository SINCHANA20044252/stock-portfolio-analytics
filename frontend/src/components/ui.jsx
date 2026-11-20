import { useCallback, useEffect, useRef, useState } from 'react'
import { PERIODS, PERIOD_LABELS } from '../lib/periods'

// Runs an async loader and tracks loading / error state. `reload` re-runs it.
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: '', loading: true })
  const run = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: '' }))
    return fn().then((data) => setState({ data, error: '', loading: false }), (e) => setState((s) => ({ ...s, error: e.message, loading: false })))
  }, deps) // eslint-disable-line
  useEffect(() => { run() }, [run])
  return { ...state, reload: run }
}

export function Skeleton({ h = 18, w = '100%', style }) {
  return <div className="skeleton" style={{ height: h, width: w, ...style }} aria-hidden="true" />
}

export function PageSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <div className="kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="card"><Skeleton w="50%" /><Skeleton h={30} style={{ marginTop: 12 }} /></div>)}</div>
      <div className="card"><Skeleton h={220} /></div>
    </div>
  )
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="errorbox" role="alert">
      <strong>Could not load this.</strong> <span>{message}</span>
      {onRetry && <button className="btn small" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Card({ title, subtitle, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div><h2>{title}</h2>{subtitle && <p className="muted small-text">{subtitle}</p>}</div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone = '' }) {
  return (
    <div className="card stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone}`}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export function PeriodFilter({ value, onChange }) {
  return (
    <div className="seg" role="group" aria-label="Time period">
      {PERIODS.map((p) => (
        <button key={p} className={p === value ? 'on' : ''} aria-pressed={p === value} title={PERIOD_LABELS[p]} onClick={() => onChange(p)}>{p === 'ALL' ? 'All' : p}</button>
      ))}
    </div>
  )
}

export function Notes({ items }) {
  if (!items?.length) return null
  return <ul className="notes">{items.map((n) => <li key={n}>{n}</li>)}</ul>
}

// Accessible modal: Esc closes, focus moves inside and returns afterwards.
export function Modal({ title, onClose, children, wide }) {
  const ref = useRef(null)
  useEffect(() => {
    const prev = document.activeElement
    ref.current?.focus()
    const key = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); prev?.focus?.() }
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <header className="card-head"><h2>{title}</h2><button className="btn ghost small" onClick={onClose} aria-label="Close">✕</button></header>
        {children}
      </div>
    </div>
  )
}

export function ConfirmDialog({ title, message, confirmLabel = 'Delete', danger = true, onConfirm, onCancel, busy }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p>{message}</p>
      <div className="row end">
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className={`btn ${danger ? 'danger' : 'primary'}`} onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>
      </div>
    </Modal>
  )
}

export function usePersistentState(key, initial) {
  const [v, setV] = useState(() => { try { return localStorage.getItem(key) ?? initial } catch { return initial } })
  const set = (x) => { setV(x); try { localStorage.setItem(key, x) } catch { /* ignore */ } }
  return [v, set]
}
