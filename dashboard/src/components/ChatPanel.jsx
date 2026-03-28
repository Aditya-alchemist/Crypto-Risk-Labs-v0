import { useState } from 'react'

export default function ChatPanel({ onAnalyze, busy }) {
  const [input, setInput] = useState('')
  const quickPrompts = [
    'Analyze BTC if 5m closes above resistance',
    'Build a short setup with conservative risk',
    'I want to buy breakout with 3 targets',
  ]

  async function submit(event) {
    event.preventDefault()
    const text = input.trim()
    if (!text) return
    setInput('')
    await onAnalyze(text)
  }

  return (
    <section className="card chat-panel">
      <h2>AI Analysis Studio</h2>
      <p className="hint">Describe your trade idea naturally. CRL will return entry, targets, SL, and confidence stack.</p>
      <div className="quick-prompt-row">
        {quickPrompts.map((prompt) => (
          <button key={prompt} type="button" className="ghost-button" onClick={() => setInput(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="chat-form">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Example: I am buying at 84,200 after box breakout, give a strict plan"
          rows={4}
        />
        <button type="submit" disabled={busy}>{busy ? 'Analyzing Setup...' : 'Run Analysis'}</button>
      </form>
    </section>
  )
}
