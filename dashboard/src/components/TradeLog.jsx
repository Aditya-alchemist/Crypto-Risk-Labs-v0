import React from 'react'

export default function TradeLog({ trades }) {
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
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id}>
              <td>{trade.pattern}</td>
              <td>{trade.side}</td>
              <td>{Number(trade.entry_price).toLocaleString()}</td>
              <td>{trade.result}</td>
              <td>{trade.rr}</td>
            </tr>
          ))}
          {trades.length === 0 ? (
            <tr>
              <td colSpan="5">No trades logged yet.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </section>
  )
}
