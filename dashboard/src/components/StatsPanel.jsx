import React from 'react'

export default function StatsPanel({ price, levelsCount, tradesCount, analytics }) {
  const momentum = Number(analytics?.momentum_pct || 0)

  return (
    <section className="card stats-grid">
      <h2>Market Snapshot</h2>
      <div className="stat">
        <label>BTC Price</label>
        <strong>${Number(price || 0).toLocaleString()}</strong>
      </div>
      <div className="stat">
        <label>Watched Levels</label>
        <strong>{levelsCount}</strong>
      </div>
      <div className="stat">
        <label>Logged Trades</label>
        <strong>{tradesCount}</strong>
      </div>
      <div className="stat">
        <label>Volatility</label>
        <strong>{Number(analytics?.volatility_pct || 0).toFixed(3)}%</strong>
      </div>
      <div className="stat">
        <label>Momentum</label>
        <strong className={momentum >= 0 ? 'good' : 'bad'}>{momentum.toFixed(3)}%</strong>
      </div>
      <div className="stat">
        <label>Avg Pattern Hit-Rate</label>
        <strong>{Number(analytics?.average_pattern_hit_rate || 0).toFixed(1)}%</strong>
      </div>
    </section>
  )
}
