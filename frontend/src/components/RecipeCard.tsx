import { useState } from 'react'
import type { RecipeData, RecipeIngredient } from '../types'

function IngredientTable({ ingredients, total_g }: { ingredients: RecipeIngredient[]; total_g: number }) {
  return (
    <table className="w-full text-sm border-collapse mt-2 mb-3">
      <thead>
        <tr className="border-b border-stone">
          <th className="text-left py-1.5 pr-4 font-medium text-ink-muted text-xs uppercase tracking-wide">Ingredient</th>
          <th className="text-right py-1.5 pr-4 font-medium text-ink-muted text-xs uppercase tracking-wide">Qty (g)</th>
          <th className="text-right py-1.5 font-medium text-ink-muted text-xs uppercase tracking-wide">%</th>
        </tr>
      </thead>
      <tbody>
        {ingredients.map((ing, i) => (
          <tr key={i} className="border-b border-stone/40 hover:bg-linen/50">
            <td className="py-1.5 pr-4 text-ink">{ing.name}</td>
            <td className="py-1.5 pr-4 text-right tabular-nums text-ink">{ing.qty_g}</td>
            <td className="py-1.5 text-right tabular-nums text-ink-muted">
              {ing.pct != null ? `${ing.pct.toFixed(1)}%` : '—'}
            </td>
          </tr>
        ))}
        {total_g > 0 && (
          <tr className="border-t-2 border-stone">
            <td className="py-1.5 pr-4 font-semibold text-ink">Total</td>
            <td className="py-1.5 pr-4 text-right tabular-nums font-semibold text-ink">{total_g}</td>
            <td />
          </tr>
        )}
      </tbody>
    </table>
  )
}

interface Props {
  recipe: RecipeData
  defaultExpanded?: boolean
}

export default function RecipeCard({ recipe, defaultExpanded = true }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <article className="bg-white border border-stone rounded-2xl overflow-hidden shadow-sm">
      <div
        className="flex items-center justify-between px-6 py-4 cursor-pointer select-none hover:bg-linen/40"
        onClick={() => setExpanded(e => !e)}
      >
        <div>
          <h2 className="font-serif text-lg text-ink font-medium">{recipe.recipe_name}</h2>
          <p className="text-[11px] text-ink-faint mt-0.5">{recipe.source_file}</p>
        </div>
        <span className="text-ink-faint text-xs">{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div className="px-6 pb-6 divide-y divide-stone/50">
          {recipe.components.map((comp, ci) => (
            <div key={ci} className="pt-5 first:pt-2">
              {comp.component_name !== recipe.recipe_name && (
                <h3 className="font-semibold text-sm text-copper uppercase tracking-wider mb-1">
                  {comp.component_name}
                </h3>
              )}
              {comp.yield_label && (
                <p className="text-xs text-ink-muted italic mb-2">— {comp.yield_label}</p>
              )}
              {comp.ingredients.length > 0 && (
                <IngredientTable ingredients={comp.ingredients} total_g={comp.total_g} />
              )}
              {(comp.method_raw || comp.method.length > 0) && (
                <div className="mt-3">
                  <p className="text-xs font-semibold text-ink uppercase tracking-wider mb-2">Method</p>
                  {comp.method_raw ? (
                    <pre className="text-sm text-ink leading-relaxed whitespace-pre-wrap font-sans">
                      {comp.method_raw}
                    </pre>
                  ) : (
                    <ol className="space-y-1.5 text-sm text-ink leading-relaxed list-none">
                      {comp.method.map((step, si) => {
                        const isLabel = !/^\d+\./.test(step)
                        return (
                          <li
                            key={si}
                            className={isLabel
                              ? 'font-semibold text-copper-dark text-xs uppercase tracking-wide mt-3 mb-1'
                              : ''}
                          >
                            {step}
                          </li>
                        )
                      })}
                    </ol>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}
