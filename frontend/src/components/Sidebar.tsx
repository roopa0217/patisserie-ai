import { useEffect, useState } from 'react'
import { fetchStats } from '../api/client'

export type View = 'search' | 'chat' | 'upload'

interface Props {
  activeView: View
  onViewChange: (v: View) => void
}


function UploadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <path d="M7 9V3m0 0L4.5 5.5M7 3l2.5 2.5" />
      <path d="M2 11a2 2 0 002 2h6a2 2 0 002-2" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <circle cx="6" cy="6" r="4" />
      <path d="M12 12L9.5 9.5" />
    </svg>
  )
}

function ChatIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8a2 2 0 01-2 2H4l-2 2V4a2 2 0 012-2h6a2 2 0 012 2v4z" />
    </svg>
  )
}

const NAV: { id: View; label: string; Icon: () => JSX.Element }[] = [
  { id: 'search', label: 'Search Recipes', Icon: SearchIcon },
  { id: 'chat',   label: 'AI Assistant',   Icon: ChatIcon },
  { id: 'upload', label: 'Upload Recipe Books', Icon: UploadIcon },
]

export default function Sidebar({ activeView, onViewChange }: Props) {
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const check = async () => {
      try { await fetchStats(); setConnected(true) }
      catch { setConnected(false) }
    }
    check()
    const t = setInterval(check, 15_000)
    return () => clearInterval(t)
  }, [])

  return (
    <aside className="w-56 shrink-0 flex flex-col h-screen"
      style={{ background: '#F0DECE', borderRight: '1px solid #D8C4AE' }}>

      {/* Brand */}
      <div className="px-6 pt-8 pb-7" style={{ borderBottom: '1px solid #D8C4AE' }}>
        <div className="flex items-center gap-2.5 mb-1">
          <span className="text-2xl leading-none select-none">🥐</span>
          <h1 className="font-serif text-lg text-ink font-medium tracking-wide leading-tight">
            Pâtisserie AI
          </h1>
        </div>
        <p className="text-[9px] tracking-[0.28em] uppercase mt-1" style={{ color: '#9A7258' }}>
          Chef Intelligence System
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-5 flex flex-col gap-0.5">
        {NAV.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => onViewChange(id)}
            className={`
              w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm text-left
              transition-all duration-150 select-none
              ${activeView === id
                ? 'bg-copper text-white font-medium shadow-sm'
                : 'text-ink-muted font-light hover:bg-copper/10 hover:text-copper'
              }
            `}
          >
            <span className="shrink-0"><Icon /></span>
            <span className="leading-snug">{label}</span>
          </button>
        ))}
      </nav>

      {/* Status */}
      <div className="px-6 py-4 flex items-center gap-2" style={{ borderTop: '1px solid #D8C4AE' }}>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? 'bg-pass-green' : 'bg-fail-red'}`} />
        <span className="text-[10px] font-light tracking-wide" style={{ color: '#9A7258' }}>
          {connected ? 'Connected' : 'Offline'}
        </span>
      </div>
    </aside>
  )
}
