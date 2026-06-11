import { useEffect, useState } from 'react'

interface Props { onDone: () => void }

export default function SplashScreen({ onDone }: Props) {
  const [exiting, setExiting] = useState(false)

  useEffect(() => {
    const t1 = setTimeout(() => setExiting(true), 1700)
    const t2 = setTimeout(onDone, 2350)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [onDone])

  return (
    <div
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center
        bg-[#0C0608] select-none
        transition-all duration-700 ease-in-out
        ${exiting ? 'opacity-0 scale-[1.04]' : 'opacity-100 scale-100'}
      `}
    >
      {/* Croissant */}
      <div className="text-7xl leading-none mb-7 animate-splash-in">
        🥐
      </div>

      {/* Title */}
      <h1
        className="font-serif text-[2.6rem] font-medium tracking-wide text-[#F2E4D0] leading-tight
          animate-fade-up"
        style={{ animationDelay: '0.15s' }}
      >
        Pâtisserie AI
      </h1>

      {/* Divider line */}
      <div
        className="h-px bg-[#B01830] my-5 origin-center animate-line-grow"
        style={{ width: '3.5rem' }}
      />

      {/* Subtitle */}
      <p
        className="text-[9px] tracking-[0.45em] uppercase animate-fade-up"
        style={{ animationDelay: '0.45s', color: '#C4A888' }}
      >
        Chef Intelligence System
      </p>

      {/* Bottom glow */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-64 h-32
        bg-[#B01830]/12 blur-3xl pointer-events-none" />
    </div>
  )
}
