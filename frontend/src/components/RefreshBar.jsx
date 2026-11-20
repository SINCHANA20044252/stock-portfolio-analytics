import { useEffect, useState } from 'react'
import { api } from '../api'
import { useToast } from '../context/AppContext'
import { timeAgo } from '../lib/format'

// "Refresh prices" button + last-updated time + provider/demo banner + per-symbol failures.
export default function RefreshBar({ asOf, onRefreshed }) {
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState([])

  useEffect(() => { api.marketStatus().then(setStatus).catch(() => {}) }, [])

  async function refresh() {
    setBusy(true); setFailed([])
    try {
      const r = await api.refreshPrices()
      setFailed(r.failed)
      if (r.failed.length) toast.error(`${r.updated.length} updated, ${r.failed.length} failed`)
      else toast.success(`Prices updated for ${r.updated.length} stock(s)`)
      onRefreshed?.()
    } catch (e) { toast.error(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="refresh">
      {status && !status.live && <div className="banner warn"><strong>Demo mode.</strong> {status.note} Prices you enter yourself still work.</div>}
      <div className="row between wrap">
        <span className="muted small-text">
          Prices updated {asOf ? timeAgo(asOf) : 'never'}{status?.live ? ` · source: ${status.provider} (delayed, unofficial)` : ''}
        </span>
        <button className="btn" onClick={refresh} disabled={busy || (status && !status.live)}>{busy ? 'Refreshing…' : '↻ Refresh prices'}</button>
      </div>
      {failed.length > 0 && (
        <ul className="notes">{failed.map((f) => <li key={f.symbol + f.reason}><b>{f.symbol}</b>: {f.reason}</li>)}</ul>
      )}
    </div>
  )
}
