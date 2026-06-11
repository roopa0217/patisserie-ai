import { useCallback, useState } from 'react'
import { streamChat } from '../api/client'
import type { Message, MessageMeta, StructuredResult } from '../types'

function uid() {
  return Math.random().toString(36).slice(2)
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)

  const sendMessage = useCallback(async (text: string) => {
    if (streaming) return

    const userMsg: Message = { id: uid(), role: 'user', content: text }
    const assistantId = uid()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      statusSteps: [],
      streaming: true,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    const history = messages.map(m => ({ role: m.role, content: m.content }))

    await streamChat(text, history, {
      onStatus(step) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, statusSteps: [...(m.statusSteps ?? []), step] }
              : m,
          ),
        )
      },
      onToken(token) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId ? { ...m, content: m.content + token } : m,
          ),
        )
      },
      onResult(result) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, structuredResult: result as StructuredResult }
              : m,
          ),
        )
      },
      onMeta(meta) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, meta: meta as MessageMeta }
              : m,
          ),
        )
      },
      onDone() {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        )
        setStreaming(false)
      },
      onError(err) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, content: `Error: ${err}`, streaming: false }
              : m,
          ),
        )
        setStreaming(false)
      },
    })
  }, [messages, streaming])

  const clearChat = useCallback(() => {
    setMessages([])
    setStreaming(false)
  }, [])

  return { messages, streaming, sendMessage, clearChat }
}
