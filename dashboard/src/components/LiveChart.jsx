import { useEffect, useRef } from 'react'

export default function LiveChart({ price, levels }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) {
      return undefined
    }

    containerRef.current.innerHTML = ''

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: 'BITSTAMP:BTCUSD',
      interval: '5',
      timezone: 'Etc/UTC',
      theme: 'light',
      style: '1',
      locale: 'en',
      enable_publishing: false,
      hide_side_toolbar: false,
      allow_symbol_change: true,
      calendar: false,
      support_host: 'https://www.tradingview.com',
    })

    const widgetHost = document.createElement('div')
    widgetHost.className = 'tradingview-widget-container'
    widgetHost.style.height = '100%'
    widgetHost.style.width = '100%'

    const widgetBody = document.createElement('div')
    widgetBody.className = 'tradingview-widget-container__widget'
    widgetBody.style.height = 'calc(100% - 24px)'
    widgetBody.style.width = '100%'
    widgetHost.appendChild(widgetBody)
    widgetHost.appendChild(script)
    containerRef.current.appendChild(widgetHost)

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = ''
      }
    }
  }, [])

  return (
    <section className="card chart-card">
      <h2>Live BTC Structure Map (TradingView 5m)</h2>
      <div className="price">${Number(price || 0).toLocaleString()}</div>
      <div ref={containerRef} className="tv-chart" />
      <div className="levels-overlay">
        {levels.map((level) => (
          <div key={level.id} className="level-row">
            <span>{level.label || 'Level'}</span>
            <span>${Number(level.price).toLocaleString()}</span>
          </div>
        ))}
      </div>
      <p className="hint">TradingView feed with your watched levels and instant visual context under the chart.</p>
    </section>
  )
}
