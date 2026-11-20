import { useState } from 'react'
import { api } from '../api'
import { Card, ErrorState, PeriodFilter, useAsync } from '../components/ui'
import { useAuth, useTheme, useToast } from '../context/AppContext'

export default function SettingsPage() {
  const toast = useToast()
  const { user, setUser } = useAuth()
  const { theme, setTheme } = useTheme()
  const prefs = useAsync(() => api.preferences(), [])
  const audit = useAsync(() => api.audit(), [])
  const [name, setName] = useState(user.display_name || '')
  const [pw, setPw] = useState({ current: '', next: '' })
  const [pwError, setPwError] = useState('')
  const [bench, setBench] = useState(null)

  const savePrefs = async (patch) => {
    const merged = { ...prefs.data, ...patch }
    try { await api.savePreferences(merged); prefs.reload(); toast.success('Saved') } catch (e) { toast.error(e.message) }
  }

  return (
    <>
      <Card title="Profile">
        <form className="row wrap" onSubmit={async (e) => { e.preventDefault(); try { setUser(await api.updateMe(name)); toast.success('Profile updated') } catch (err) { toast.error(err.message) } }}>
          <label>Display name<input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
          <label>Email<input value={user.email} disabled /></label>
          <button className="btn primary">Save</button>
        </form>
      </Card>

      <Card title="Appearance and defaults">
        {prefs.error ? <ErrorState message={prefs.error} onRetry={prefs.reload} /> : (
          <div className="stack">
            <div className="row wrap"><span>Theme</span>
              <div className="seg">{['light', 'dark', 'system'].map((t) => <button key={t} className={theme === t ? 'on' : ''} onClick={() => { setTheme(t); if (prefs.data) savePrefs({ theme: t }) }}>{t}</button>)}</div></div>
            <div className="row wrap"><span>Default period</span>{prefs.data && <PeriodFilter value={prefs.data.default_period} onChange={(p) => { try { localStorage.setItem('period', p) } catch { /* ignore */ } savePrefs({ default_period: p }) }} />}</div>
            <form className="row wrap" onSubmit={(e) => { e.preventDefault(); savePrefs({ benchmark_symbol: bench ?? prefs.data?.benchmark_symbol ?? '' }) }}>
              <label>Benchmark symbol (optional)<input defaultValue={prefs.data?.benchmark_symbol || ''} onChange={(e) => setBench(e.target.value)} placeholder="^NSEI" maxLength={20} /></label>
              <button className="btn">Save</button>
            </form>
          </div>)}
      </Card>

      <Card title="Change password" subtitle="Signs you out on other devices.">
        <form className="row wrap" onSubmit={async (e) => {
          e.preventDefault(); setPwError('')
          try { await api.changePassword(pw.current, pw.next); setPw({ current: '', next: '' }); toast.success('Password changed') } catch (err) { setPwError(err.message) }
        }}>
          <label>Current password<input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} required /></label>
          <label>New password (8+ characters)<input type="password" autoComplete="new-password" minLength={8} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} required /></label>
          <button className="btn primary">Change</button>
        </form>
        {pwError && <div className="errorbox" role="alert">{pwError}</div>}
      </Card>

      <Card title="Recent activity" subtitle="Every change to your data is logged.">
        {audit.error ? <ErrorState message={audit.error} onRetry={audit.reload} /> : (
          <div className="table-wrap tall"><table><thead><tr><th>When</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{(audit.data || []).map((a, i) => <tr key={i}><td>{new Date(a.at).toLocaleString('en-IN')}</td><td>{a.action}</td><td className="small-text">{a.detail}</td></tr>)}</tbody></table></div>)}
      </Card>
    </>
  )
}
