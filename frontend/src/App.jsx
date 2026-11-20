import { useEffect, useState } from 'react'
import Layout from './components/Layout'
import { useAuth } from './context/AppContext'
import AskAI from './pages/AskAI'
import Dashboard from './pages/Dashboard'
import DataPage from './pages/DataPage'
import Goals from './pages/Goals'
import Holdings from './pages/Holdings'
import Login from './pages/Login'
import Performance from './pages/Performance'
import Risk from './pages/Risk'
import SettingsPage from './pages/SettingsPage'
import Transactions from './pages/Transactions'

export const PAGES = [
  { id: 'dashboard', label: 'Dashboard', title: 'Dashboard', blurb: 'Your portfolio at a glance: value, returns and allocation.', C: Dashboard },
  { id: 'holdings', label: 'Holdings', title: 'Holdings', blurb: 'What you own today, with live or manual prices.', C: Holdings },
  { id: 'transactions', label: 'Transactions', title: 'Transaction history', blurb: 'Every buy and sell. Edit or delete with checks that keep your holdings valid.', C: Transactions },
  { id: 'performance', label: 'Performance', title: 'Performance analytics', blurb: 'Returns over time, rebuilt from your transactions and stored closing prices.', C: Performance },
  { id: 'risk', label: 'Risk', title: 'Risk analysis', blurb: 'Concentration, volatility and drawdown, with how each is calculated.', C: Risk },
  { id: 'goals', label: 'Goal planner', title: 'SIP and goal planner', blurb: 'Estimate the monthly SIP you need and compare scenarios.', C: Goals },
  { id: 'ai', label: 'Ask AI', title: 'AI finance assistant', blurb: 'Questions about your own portfolio and investing terms.', C: AskAI },
  { id: 'data', label: 'Import / Export', title: 'Import and export', blurb: 'Bring in CSV or Excel files and download reports.', C: DataPage },
  { id: 'settings', label: 'Settings', title: 'Settings', blurb: 'Profile, appearance, security and activity.', C: SettingsPage },
]

const fromHash = () => PAGES.find((p) => p.id === window.location.hash.slice(1))?.id || 'dashboard'

export default function App() {
  const { user } = useAuth()
  const [page, setPage] = useState(fromHash)
  // Bump to make pages reload after data changes elsewhere.
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const onHash = () => setPage(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = (id) => { window.location.hash = id; setPage(id) }

  if (user === undefined) return <div className="boot">Loading…</div>
  if (user === null) return <Login />
  const current = PAGES.find((p) => p.id === page)
  const Page = current.C
  return (
    <Layout pages={PAGES} current={current} go={go}>
      <Page key={current.id + version} go={go} changed={() => setVersion((v) => v + 1)} />
    </Layout>
  )
}
