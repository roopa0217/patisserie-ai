import type { Message, Stats } from '../types'

// In dev, call the backend directly (CORS is open on the API).
// In prod, use relative paths (backend serves on same origin).
const BASE = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''

export async function fetchStats(): Promise<Stats> {
  const r = await fetch(`${BASE}/stats`)
  if (!r.ok) throw new Error('Stats fetch failed')
  return r.json()
}

export async function uploadPdf(file: File): Promise<{ chunks: number; recipes: number; status: string }> {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${BASE}/ingest/upload`, { method: 'POST', body: form })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(err.detail || 'Upload failed')
  }
  return r.json()
}

type SSEHandler = {
  onStatus: (step: string) => void
  onToken: (token: string) => void
  onResult: (result: unknown) => void
  onMeta: (meta: unknown) => void
  onDone: () => void
  onError: (err: string) => void
}

export async function streamChat(
  message: string,
  history: Array<{ role: string; content: string }>,
  handlers: SSEHandler,
): Promise<void> {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })

  if (!response.ok || !response.body) {
    handlers.onError('Failed to connect to the server.')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const event = JSON.parse(line.slice(6))
        switch (event.type) {
          case 'status':   handlers.onStatus(event.content); break
          case 'token':    handlers.onToken(event.content); break
          case 'result':   handlers.onResult(event.content); break
          case 'meta':     handlers.onMeta(event.content); break
          case 'done':     handlers.onDone(); break
          case 'error':    handlers.onError(event.content); break
        }
      } catch {
        // ignore malformed lines
      }
    }
  }
}
