import { useState } from 'react'
import { useAuth } from '../context/AppContext'

export default function Login() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try { await (mode === 'login' ? login : register)(email, password) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="auth">
      <section className="auth-pitch">
        <div className="brand"><span className="brand-mark">P</span> Portfolio Tracker</div>
        <h1>Know what you own, what it earned and where the risk sits.</h1>
        <ul>
          <li>Track buys and sells with weighted-average cost</li>
          <li>Returns, volatility and drawdown from real price history</li>
          <li>Plan SIPs and ask questions about your own numbers</li>
        </ul>
        <p className="small-text">Educational project. Not investment advice.</p>
      </section>
      <section className="auth-form">
        <form onSubmit={submit} className="card" noValidate>
          <h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
          <label>Email<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Password
            <span className="pw">
              <input type={show ? 'text' : 'password'} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required />
              <button type="button" className="btn ghost small" onClick={() => setShow(!show)}>{show ? 'Hide' : 'Show'}</button>
            </span>
          </label>
          {mode === 'register' && <p className="hint">At least 8 characters.</p>}
          {error && <div className="errorbox" role="alert">{error}</div>}
          <button className="btn primary block" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}</button>
          <p className="switch">
            {mode === 'login' ? 'New here?' : 'Already have an account?'}{' '}
            <button type="button" className="link" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>
              {mode === 'login' ? 'Create an account' : 'Log in'}
            </button>
          </p>
        </form>
      </section>
    </div>
  )
}
