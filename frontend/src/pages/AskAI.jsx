import { useRef, useState } from 'react'
import { api } from '../api'
import { Card } from '../components/ui'

const SUGGESTIONS = [
  'What is my total portfolio value?', 'Which stock has the highest allocation?', 'Which sector has the highest exposure?',
  'Which stock generated the highest return?', 'What is my overall profit/loss?', 'Explain my portfolio diversification.',
  'What does maximum drawdown mean?', 'Explain the risk associated with my portfolio concentration.', 'Summarize my monthly portfolio performance.',
]

export default function AskAI() {
  const [q, setQ] = useState('')
  const [chat, setChat] = useState([])
  const [busy, setBusy] = useState(false)
  const end = useRef(null)

  async function ask(text) {
    const question = text.trim()
    if (question.length < 3 || busy) return
    setChat((c) => [...c, { role: 'user', text: question }]); setQ(''); setBusy(true)
    try {
      const r = await api.ask(question)
      setChat((c) => [...c, { role: 'ai', ...r }])
    } catch (e) {
      setChat((c) => [...c, { role: 'ai', error: true, answer: e.status === 429 ? e.message : 'The assistant is unavailable right now. Your portfolio pages still work; please try again in a moment.' }])
    } finally { setBusy(false); setTimeout(() => end.current?.scrollIntoView({ behavior: 'smooth' }), 50) }
  }

  return (
    <>
      <Card title="Ask a question" subtitle="Answers about your portfolio use only your own saved data. Glossary answers explain terms.">
        <div className="suggest">{SUGGESTIONS.map((s) => <button key={s} className="chipbtn" onClick={() => ask(s)} disabled={busy}>{s}</button>)}</div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. What is an index fund?" maxLength={300} aria-label="Your question" />
          <button className="btn primary" disabled={busy || q.trim().length < 3}>{busy ? 'Thinking…' : 'Ask'}</button>
        </form>
      </Card>
      <div className="chat" aria-live="polite">
        {chat.map((m, i) => m.role === 'user' ? <div key={i} className="bubble me">{m.text}</div> : (
          <div key={i} className={`bubble ai ${m.error ? 'err' : ''}`}>
            <p>{m.answer}</p>
            {!m.error && (
              <div className="meta">
                <span className={`badge ${m.grounded ? 'ok' : ''}`}>{m.grounded ? 'Grounded in your data' : 'Glossary'}</span>
                {m.used_ai && <span className="badge">AI-worded</span>}
                {m.sources?.length > 0 && <span className="muted small-text">Sources: {m.sources.join(', ')}</span>}
              </div>)}
            {m.used_ai && m.plain_answer && <details><summary>Show the exact computed answer</summary><p>{m.plain_answer}</p></details>}
          </div>))}
        <div ref={end} />
      </div>
      <p className="muted small-text">Educational information only, not investment advice.</p>
    </>
  )
}
