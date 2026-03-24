import React from 'react'

export default function LevelsPanel({ levels }) {
  return (
    <section className="card">
      <h2>Watched Levels</h2>
      <ul className="simple-list">
        {levels.map((level) => (
          <li key={level.id}>
            <span>{level.label || `Level ${level.id}`}</span>
            <span>${Number(level.price).toLocaleString()}</span>
          </li>
        ))}
        {levels.length === 0 ? <li>No levels yet.</li> : null}
      </ul>
    </section>
  )
}
