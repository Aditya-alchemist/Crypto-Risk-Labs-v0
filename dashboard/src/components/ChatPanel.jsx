import { useState } from 'react'

export default function ChatPanel({ onAnalyze, busy }) {
  const [input, setInput] = useState('')

  async function submit(event) {
    event.preventDefault()
    const text = input.trim()
    if (!text) return
    setInput('')
    await onAnalyze(text)
  }

  return (
    <section className="card chat-panel">
      <h2>AI Analysis Chat</h2>
      <form onSubmit={submit} className="chat-form">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask naturally: i want to buy at current price, analyze market and give targets"
          rows={3}
        />
        <button type="submit" disabled={busy}>{busy ? 'Analyzing...' : 'Analyze'}</button>
      </form>
    </section>
  )
}
