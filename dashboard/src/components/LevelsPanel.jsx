import React from 'react'

export default function LevelsPanel({ levels, price }) {
  return (
    <section className="card">
      <h2>Watched Levels</h2>
      <ul className="simple-list">
        {levels.map((level) => (
          <li key={level.id}>
            <span>
              <strong>{level.label || `Level ${level.id}`}</strong>
              <small className="level-distance">{(((Number(level.price) - Number(price || 0)) / Number(price || 1)) * 100).toFixed(2)}%</small>
            </span>
            <span>${Number(level.price).toLocaleString()}</span>
          </li>
        ))}
        {levels.length === 0 ? <li>No levels yet.</li> : null}
      </ul>
    </section>
  )
}
