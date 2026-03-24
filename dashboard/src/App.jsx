import { useEffect, useMemo, useState } from 'react'
import { chatAnalyze, createWs, getAnalytics, getLevels, getMonteCarlo, getPrice, getTrades } from './api'
import LiveChart from './components/LiveChart'
import StatsPanel from './components/StatsPanel'
import LevelsPanel from './components/LevelsPanel'
import MonteCarloChart from './components/MonteCarloChart'
import TradeLog from './components/TradeLog'
import ChatPanel from './components/ChatPanel'

export default function App() {
  const [price, setPrice] = useState(0)
  const [levels, setLevels] = useState([])
  const [trades, setTrades] = useState([])
  const [analytics, setAnalytics] = useState({})
  const [mc, setMc] = useState({ hit_tp_probability: 50, bins: [] })
  const [chatMessages, setChatMessages] = useState([])
  const [chatBusy, setChatBusy] = useState(false)

  useEffect(() => {
    let ws

    async function load() {
      const [p, l, t, a, m] = await Promise.all([getPrice(), getLevels(), getTrades(), getAnalytics(), getMonteCarlo()])
      setPrice(p.price || 0)
      setLevels(l)
      setTrades(t)
      setAnalytics(a || {})
      setMc(m || { hit_tp_probability: 50, bins: [] })
    }

    load().catch(console.error)

    createWs((message) => {
      if (message.type === 'price_update') {
        setPrice(message.price)
      }
      if (message.type === 'level_added') {
        setLevels((prev) => [...prev, message])
      }
      if (message.type === 'level_cross') {
        console.log('Level crossed', message)
      }
    })
      .then((connected) => {
        ws = connected
      })
      .catch(console.error)

    const priceInterval = setInterval(() => {
      getPrice().then((p) => setPrice(p.price || 0)).catch(console.error)
    }, 1000)

    const interval = setInterval(() => {
      getTrades().then(setTrades).catch(console.error)
      getLevels().then(setLevels).catch(console.error)
      getAnalytics().then(setAnalytics).catch(console.error)
      getMonteCarlo().then(setMc).catch(console.error)
    }, 2500)

    return () => {
      clearInterval(priceInterval)
      clearInterval(interval)
      if (ws) ws.close()
    }
  }, [])

  async function handleChatAnalyze(prompt) {
    setChatBusy(true)
    setChatMessages((prev) => [...prev, { role: 'user', text: prompt }])
    try {
      const response = await chatAnalyze(prompt)
      const text = response.message || 'No response generated.'
      setChatMessages((prev) => [...prev, { role: 'assistant', text }])
      if (response.plan?.entry) {
        setPrice(response.plan.entry)
      }
      if (response.monte_carlo_bins) {
        setMc((prev) => ({ ...prev, bins: response.monte_carlo_bins, hit_tp_probability: response.confidence?.monte_carlo || prev.hit_tp_probability }))
      }
    } catch (error) {
      setChatMessages((prev) => [...prev, { role: 'assistant', text: `Analysis failed: ${error.message}` }])
    } finally {
      setChatBusy(false)
    }
  }

  const winRate = useMemo(() => {
    if (trades.length === 0) return 0
    const wins = trades.filter((t) => (t.result || '').toUpperCase() === 'WIN').length
    return (wins / trades.length) * 100
  }, [trades])

  return (
    <main className="app-shell">
      <header>
        <h1>CRL Trading Intelligence</h1>
        <p>Win rate: {winRate.toFixed(1)}%</p>
      </header>

      <section className="grid">
        <LiveChart price={price} levels={levels} />
        <StatsPanel price={price} levelsCount={levels.length} tradesCount={trades.length} analytics={analytics} />
        <LevelsPanel levels={levels} />
        <MonteCarloChart probability={mc.hit_tp_probability || Math.min(90, Math.max(40, winRate || 50))} bins={mc.bins || []} />
      </section>

      <section className="grid">
        <ChatPanel onAnalyze={handleChatAnalyze} busy={chatBusy} />
        <section className="card chat-history">
          <h2>Conversation</h2>
          <div className="chat-scroll">
            {chatMessages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role}`}>
                {m.text}
              </div>
            ))}
            {chatMessages.length === 0 ? <p className="hint">Ask for market analysis in natural language.</p> : null}
          </div>
        </section>
      </section>

      <TradeLog trades={trades} />
    </main>
  )
}
