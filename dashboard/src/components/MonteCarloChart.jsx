import React from 'react'

export default function MonteCarloChart({ probability = 0, bins = [] }) {
  const clamped = Math.max(0, Math.min(100, probability))
  const maxCount = bins.length > 0 ? Math.max(...bins.map((b) => b.count || 0)) : 1

  return (
    <section className="card">
      <h2>Monte Carlo Distribution</h2>
      <div className="mc-bars">
        {bins.map((b, i) => (
          <div
            key={`${b.bin_start}-${i}`}
            className="mc-bar"
            title={`${b.bin_start} - ${b.bin_end} : ${b.count}`}
            style={{ height: `${Math.max(6, ((b.count || 0) / maxCount) * 100)}%` }}
          />
        ))}
      </div>
      <p>Estimated probability of TP before SL: <strong>{clamped.toFixed(1)}%</strong></p>
    </section>
  )
}
