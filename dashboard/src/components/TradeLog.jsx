import React from 'react'

export default function TradeLog({ trades }) {
  function formatTime(value) {
    if (!value) return '-'
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return '-'
    return d.toLocaleString()
  }

  return (
    <section className="card trade-log">
      <h2>Trade Log</h2>
      <table>
        <thead>
          <tr>
            <th>Pattern</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Result</th>
            <th>RR</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id}>
              <td>{trade.pattern}</td>
              <td>{trade.side}</td>
              <td>{Number(trade.entry_price).toLocaleString()}</td>
              <td>
                <span className={`result-chip ${(trade.result || '').toUpperCase() === 'WIN' ? 'win' : 'loss'}`}>
                  {trade.result || '-'}
                </span>
              </td>
              <td>{trade.rr}</td>
              <td>{formatTime(trade.created_at)}</td>
            </tr>
          ))}
          {trades.length === 0 ? (
            <tr>
              <td colSpan="6">No trades logged yet.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </section>
  )
}
