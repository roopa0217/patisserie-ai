import { useState } from 'react'
import ChatArea from './components/ChatArea'
import Sidebar, { type View } from './components/Sidebar'
import SplashScreen from './components/SplashScreen'
import UploadView from './views/UploadView'
import RecipeSearchView from './views/RecipeSearchView'
import { useChat } from './hooks/useChat'
import type { Suggestion } from './components/ChatArea'

const CHAT_SUGGESTIONS: Suggestion[] = [
  { label: 'Scale yield',    text: 'Scale the berliner doughnut to 2000g' },
  { label: 'Indent sheet',   text: 'Build an indent sheet for soft rolls and berliner doughnuts' },
  { label: 'Baking science', text: 'Why does over-proofing happen in enriched doughs?' },
  { label: 'Check ratios',   text: 'Check the soft rolls recipe for anomalies' },
]

export default function App() {
  const [showSplash, setShowSplash] = useState(true)
  const [view, setView] = useState<View>('search')
  const chat = useChat()

  if (showSplash) {
    return <SplashScreen onDone={() => setShowSplash(false)} />
  }

  return (
    <div className="flex h-screen overflow-hidden animate-fade-in">
      <Sidebar activeView={view} onViewChange={setView} />

      <main className="flex-1 flex flex-col min-w-0">

        {view === 'search' && <RecipeSearchView />}

        {view === 'chat' && (
          <ChatArea
            messages={chat.messages}
            streaming={chat.streaming}
            onSend={chat.sendMessage}
            clearChat={chat.clearChat}
            suggestions={CHAT_SUGGESTIONS}
            placeholder="Scale yields, build indent sheets, ask baking questions…"
            emptyTitle="AI Assistant"
            emptySubtitle="Scale recipes, build indent sheets, ask baking questions"
          />
        )}

        {view === 'upload' && <UploadView />}

      </main>
    </div>
  )
}
