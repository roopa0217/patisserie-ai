import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import type { Message } from '../types/index'

export interface Suggestion {
  label: string
  text: string
}

interface Props {
  messages: Message[]
  streaming: boolean
  onSend: (text: string) => void
  clearChat: () => void
  suggestions: Suggestion[]
  placeholder?: string
  emptyTitle?: string
  emptySubtitle?: string
}

function SendIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
      <path d="M2 7h10M8 3l4 4-4 4" stroke="#FDFCF9" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function ChatArea({
  messages,
  streaming,
  onSend,
  clearChat,
  suggestions,
  placeholder = 'Ask a question…',
  emptyTitle = 'Pâtisserie AI',
  emptySubtitle = 'Your intelligent kitchen assistant',
}: Props) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)

  // When the user scrolls up, stop auto-scrolling. Resume when they reach the bottom.
  function onScroll() {
    const el = scrollContainerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    userScrolledUp.current = distanceFromBottom > 80
  }

  useEffect(() => {
    if (!userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  function submit() {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    onSend(text)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const inputBox = (
    <div className="flex items-end gap-3 bg-white rounded-xl border border-stone px-5 py-3.5 focus-within:border-stone-dark transition-colors shadow-sm">
      <textarea
        rows={1}
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={streaming}
        placeholder={streaming ? 'Thinking…' : placeholder}
        className="
          flex-1 resize-none bg-transparent text-sm text-ink font-light
          placeholder:text-ink-faint/60
          focus:outline-none disabled:opacity-40
          max-h-28 leading-relaxed
        "
        style={{ fieldSizing: 'content' } as React.CSSProperties}
      />
      <button
        onClick={submit}
        disabled={streaming || !input.trim()}
        className="
          shrink-0 w-8 h-8 rounded-full
          bg-copper hover:bg-copper-light
          disabled:opacity-20 disabled:cursor-not-allowed
          flex items-center justify-center transition-colors
        "
        aria-label="Send"
      >
        <SendIcon />
      </button>
    </div>
  )

  // ── Empty / landing state: everything centered ──────────────────────────────
  if (messages.length === 0) {
    return (
      <div className="flex flex-col flex-1 min-h-0 bg-parchment items-center justify-center px-8 animate-fade-in">

        <h1 className="font-serif text-4xl text-ink font-medium mb-3 tracking-wide text-center leading-tight">
          {emptyTitle}
        </h1>
        <p className="text-ink-faint text-sm mb-10 tracking-wide font-light text-center">
          {emptySubtitle}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg mb-8">
          {suggestions.map(s => (
            <button
              key={s.label}
              onClick={() => onSend(s.text)}
              className="
                text-left rounded-xl border border-stone bg-white
                px-5 py-4 hover:border-stone-dark hover:shadow-sm
                transition-all duration-200 group
              "
            >
              <p className="text-[9px] font-medium text-copper uppercase tracking-[0.2em] mb-1.5">
                {s.label}
              </p>
              <p className="text-sm text-ink-muted group-hover:text-ink transition-colors leading-snug font-light">
                {s.text}
              </p>
            </button>
          ))}
        </div>

        <div className="w-full max-w-lg">
          {inputBox}
        </div>

        <div className="mt-10 h-px w-24 bg-stone" />
      </div>
    )
  }

  // ── Conversation state: messages scroll + input pinned at bottom ────────────
  return (
    <div className="flex flex-col flex-1 min-h-0 bg-parchment">

      <div className="shrink-0 border-b border-stone bg-sand px-8 py-3 flex items-center gap-2.5">
        <span className="font-serif text-sm text-ink font-medium tracking-wide">{emptyTitle}</span>
      </div>

      <div ref={scrollContainerRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-8 py-8 flex flex-col gap-6 max-w-4xl mx-auto w-full">
        {messages.map(m => <MessageBubble key={m.id} message={m} />)}
        {!streaming && (
          <div className="flex justify-center pt-2">
            <button
              onClick={clearChat}
              className="text-[10px] text-ink-faint hover:text-ink-muted transition-colors font-light tracking-wide px-3 py-1.5 rounded-lg hover:bg-linen"
            >
              Clear conversation
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-stone bg-sand px-8 py-5 max-w-4xl mx-auto w-full">
        {inputBox}
      </div>
    </div>
  )
}
