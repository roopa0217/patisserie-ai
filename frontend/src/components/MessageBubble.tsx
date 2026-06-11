import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import AnomalyCard from './AnomalyCard'
import Citations from './Citations'
import IndentTable from './IndentTable'
import RecipeCard from './RecipeCard'
import ScaleTable from './ScaleTable'
import StatusSteps from './StatusSteps'
import type { Message } from '../types/index'

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="max-w-[68%] rounded-2xl rounded-tr-sm bg-copper px-5 py-3.5 text-sm text-parchment font-light leading-relaxed shadow-sm">
          {message.content}
        </div>
      </div>
    )
  }

  const isStreaming = message.streaming
  const hasMeta = !!message.meta
  const steps = message.statusSteps ?? []

  return (
    <div className="flex justify-start animate-slide-up">
      <div className="max-w-[88%] rounded-2xl rounded-tl-sm bg-white border border-stone px-6 py-5 shadow-sm">

        <StatusSteps steps={steps} done={!isStreaming} />

        {isStreaming && !message.content && steps.length === 0 && (
          <div className="flex gap-1.5 py-1">
            {[0, 1, 2].map(d => (
              <span
                key={d}
                className="w-1.5 h-1.5 rounded-full bg-stone-dark animate-pulse-dot"
                style={{ animationDelay: `${d * 0.16}s` }}
              />
            ))}
          </div>
        )}

        {message.structuredResult?.type === 'recipe_results' && (() => {
          const recipes = message.structuredResult.data.recipes
          return (
            <div className="space-y-3 mt-1">
              {recipes.map(recipe => (
                <RecipeCard key={recipe.recipe_name} recipe={recipe} defaultExpanded={recipes.length === 1} />
              ))}
            </div>
          )
        })()}

        {message.content && message.structuredResult?.type !== 'recipe_results' && (
          <div className="text-sm text-ink font-light leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => (
                  <h1 className="font-serif text-lg text-ink font-medium mb-2 mt-1">{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 className="font-serif text-base text-copper mb-2 mt-4 font-medium">{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-sm font-medium text-ink mb-1 mt-3">{children}</h3>
                ),
                strong: ({ children }) => (
                  <strong className="font-medium text-ink">{children}</strong>
                ),
                p: ({ children }) => (
                  <p className="mb-2.5 last:mb-0 leading-relaxed text-ink-muted">{children}</p>
                ),
                ul: ({ children }) => (
                  <ul className="mb-2 pl-4 list-disc space-y-1">{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol className="mb-2 pl-4 list-decimal space-y-1">{children}</ol>
                ),
                li: ({ children }) => <li className="text-ink-muted">{children}</li>,
                table: ({ children }) => (
                  <div className="overflow-x-auto my-3 rounded-lg border border-stone">
                    <table className="text-xs border-collapse w-full">{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="bg-linen border-b border-stone px-3 py-2 text-left text-ink-faint text-[9px] uppercase tracking-[0.15em] font-medium">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border-b border-stone/30 px-3 py-2 text-ink-muted font-light">{children}</td>
                ),
                code: ({ children }) => (
                  <code className="bg-linen text-copper px-1.5 py-0.5 rounded text-xs">{children}</code>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-stone-dark pl-3 my-2 text-ink-faint italic font-light">
                    {children}
                  </blockquote>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {message.structuredResult?.type === 'scale_results' && (
          <ScaleTable results={message.structuredResult.data} />
        )}
        {message.structuredResult?.type === 'anomaly_report' && (
          <AnomalyCard report={message.structuredResult.data} />
        )}
        {message.structuredResult?.type === 'indent_sheet' && (
          <IndentTable sheet={message.structuredResult.data} />
        )}

        {hasMeta && !isStreaming && message.meta!.sources.length > 0 && (
          <Citations sources={message.meta!.sources} />
        )}
      </div>
    </div>
  )
}
