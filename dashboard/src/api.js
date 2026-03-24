const ENV_API_BASE = import.meta.env.VITE_BACKEND_URL
let resolvedApiBasePromise

function candidateBases() {
  const host = window.location.hostname || 'localhost'
  const unique = new Set([
    ENV_API_BASE,
    `http://${host}:8001`,
    'http://127.0.0.1:8001',
    `http://${host}:8000`,
    'http://127.0.0.1:8000',
  ].filter(Boolean))
  return [...unique]
}

async function hasRequiredRoutes(base) {
  try {
    const r = await fetch(`${base}/openapi.json`)
    if (!r.ok) return false
    const doc = await r.json()
    const paths = doc?.paths || {}
    return Boolean(paths['/api/chat-analyze'] && paths['/api/monte-carlo'] && paths['/api/analytics'])
  } catch {
    return false
  }
}

async function resolveApiBase() {
  for (const base of candidateBases()) {
    if (await hasRequiredRoutes(base)) {
      return base
    }
  }
  return ENV_API_BASE || 'http://127.0.0.1:8001'
}

function getApiBase() {
  if (!resolvedApiBasePromise) {
    resolvedApiBasePromise = resolveApiBase()
  }
  return resolvedApiBasePromise
}

async function apiFetch(path, options) {
  const base = await getApiBase()
  const r = await fetch(`${base}${path}`, options)
  if (!r.ok) {
    const body = await r.text().catch(() => '')
    const suffix = body ? ` (${body.slice(0, 200)})` : ''
    throw new Error(`Request failed ${r.status}${suffix}`)
  }
  return r.json()
}

export async function getPrice() {
  return apiFetch('/api/price')
}

export async function getLevels() {
  return apiFetch('/api/levels')
}

export async function getTrades() {
  return apiFetch('/api/trades')
}

export async function getAnalytics() {
  return apiFetch('/api/analytics')
}

export async function getMonteCarlo() {
  return apiFetch('/api/monte-carlo')
}

export async function chatAnalyze(prompt) {
  return apiFetch('/api/chat-analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
}

export async function createWs(onMessage) {
  const apiBase = await getApiBase()
  const wsProtocol = apiBase.startsWith('https') ? 'wss' : 'ws'
  const host = apiBase.replace(/^https?:\/\//, '')
  const ws = new WebSocket(`${wsProtocol}://${host}/ws`)
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {
      // Ignore malformed messages.
    }
  }
  return ws
}
