import { useEffect, useRef, useState } from 'react'
import RecipeCard from '../components/RecipeCard'
import type { RecipeData } from '../types'

// @ts-ignore — Vite provides import.meta.env at runtime
const API: string = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''

interface SearchResult {
  query: string
  recipes: RecipeData[]
  all_names: string[]
}

const SUGGESTIONS = [
  'Berliner doughnut',
  'Croissant',
  'Soft rolls',
  'Classic sugar glaze',
]

function isScaleQuery(q: string): boolean {
  return /\b\d[\d,.]*\s*(?:gms?|g(?:rams?)?|kg)\b/i.test(q)
}

export default function RecipeSearchView() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  async function search(q: string) {
    if (!q.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`${API}/recipes/search?q=${encodeURIComponent(q)}`)
      const data: SearchResult = await res.json()
      setResult(data)
    } catch {
      setResult({ query: q, recipes: [], all_names: [] })
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    search(query)
  }

  const isEmpty = !result && !loading

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-linen/30 h-screen overflow-hidden">

      <div className={`flex flex-col items-center px-8 transition-all duration-300 ${isEmpty ? 'pt-24' : 'pt-8'}`}>
        {isEmpty && (
          <div className="text-center mb-8">
            <h1 className="font-serif text-2xl text-ink font-medium mb-1">Recipe Search</h1>
            <p className="text-sm text-ink-muted">Find any recipe from your uploaded books — exact content, nothing changed</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="w-full max-w-xl flex gap-2">
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search by recipe name or ingredient…"
            className="flex-1 border border-stone rounded-xl px-4 py-3 text-sm bg-white text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-copper/30 shadow-sm"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-5 py-3 bg-copper text-white text-sm rounded-xl font-medium disabled:opacity-40 hover:bg-copper/90 transition-colors shadow-sm"
          >
            {loading ? '…' : 'Search'}
          </button>
        </form>

        {isEmpty && (
          <div className="flex flex-wrap gap-2 mt-5 justify-center">
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => { setQuery(s); search(s) }}
                className="px-3 py-1.5 text-xs border border-stone rounded-full bg-white text-ink-muted hover:bg-linen hover:text-ink transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-8 pb-10 mt-6">
        <div className="max-w-xl mx-auto space-y-4">
          {loading && (
            <div className="text-center text-sm text-ink-muted py-12">Searching…</div>
          )}
          {result && !loading && isScaleQuery(result.query) && (
            <div className="rounded-xl border border-copper/30 bg-copper/5 px-5 py-4 flex items-start gap-3">
              <span className="text-copper text-lg leading-none mt-0.5">⚖</span>
              <div>
                <p className="text-sm font-medium text-ink">Looks like a scaling query</p>
                <p className="text-xs text-ink-muted mt-0.5">
                  Recipe Search shows original quantities only.
                  For scaled quantities, switch to the <strong>Chat</strong> and ask the same question there.
                </p>
              </div>
            </div>
          )}
          {result && !loading && result.recipes.length === 0 && !isScaleQuery(result.query) && (
            <div className="text-center py-12">
              <p className="text-ink-muted text-sm">No recipes found for <strong>"{result.query}"</strong></p>
              <p className="text-ink-faint text-xs mt-1">Try uploading the relevant PDF via Upload Recipe Books</p>
            </div>
          )}
          {result && !loading && result.recipes.map(recipe => (
            <RecipeCard key={recipe.recipe_name} recipe={recipe} />
          ))}
        </div>
      </div>

    </div>
  )
}
