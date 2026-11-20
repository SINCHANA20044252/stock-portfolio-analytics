import { useEffect, useRef, useState } from 'react'
import { useAuth, useTheme } from '../context/AppContext'

export default function Layout({ pages, current, go, children }) {
  const { user, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const [navOpen, setNavOpen] = useState(false)
  const [menu, setMenu] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    const close = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenu(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const name = user.display_name || user.email
  const next = { light: 'dark', dark: 'system', system: 'light' }[theme]

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <aside className={`side ${navOpen ? 'open' : ''}`}>
        <div className="brand"><span className="brand-mark">P</span> Portfolio Tracker</div>
        <nav aria-label="Main">
          {pages.map((p) => (
            <button key={p.id} className={p.id === current.id ? 'active' : ''} aria-current={p.id === current.id ? 'page' : undefined}
              onClick={() => { go(p.id); setNavOpen(false) }}>{p.label}</button>
          ))}
        </nav>
        <p className="side-note">Educational project. Not investment advice.</p>
      </aside>
      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} />}

      <div className="content">
        <header className="topbar">
          <button className="btn ghost burger" aria-label="Open menu" onClick={() => setNavOpen(true)}>☰</button>
          <div className="topbar-title">{current.title}</div>
          <div className="row">
            <button className="btn ghost" onClick={() => setTheme(next)} title={`Theme: ${theme}. Click for ${next}`}>
              {theme === 'dark' ? '🌙' : theme === 'light' ? '☀️' : '🖥️'} <span className="hide-sm">{theme}</span>
            </button>
            <div className="profile" ref={menuRef}>
              <button className="avatar" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)} title={name}>{name[0].toUpperCase()}</button>
              {menu && (
                <div className="menu" role="menu">
                  <div className="menu-head"><strong>{user.display_name || 'Your account'}</strong><span className="muted small-text">{user.email}</span></div>
                  <button role="menuitem" onClick={() => { go('settings'); setMenu(false) }}>Settings</button>
                  <button role="menuitem" onClick={logout}>Log out</button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main id="main" className="main">
          <div className="page-head"><h1>{current.title}</h1><p>{current.blurb}</p></div>
          {children}
        </main>
      </div>
    </div>
  )
}
