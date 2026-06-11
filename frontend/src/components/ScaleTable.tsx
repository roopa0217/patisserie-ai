import type { ScaleResult } from '../types/index'

interface Props {
  results: ScaleResult[]
}

export default function ScaleTable({ results }: Props) {
  if (!results.length) return null

  return (
    <div className="mt-3 flex flex-col gap-5">
      {results.map((r, ri) => (
        <div key={ri} className="rounded-xl border border-stone overflow-hidden">

          {/* Component header */}
          <div className="px-4 py-2.5 bg-linen border-b border-stone flex items-center justify-between gap-4 flex-wrap">
            <div>
              <span className="font-serif text-sm text-ink font-medium">{r.component_name}</span>
              <span className="text-xs text-ink-faint ml-2 font-light">{r.recipe_name}</span>
            </div>
            <span className="text-[10px] text-ink-faint font-light shrink-0">
              {r.original_yield.toFixed(0)}g → {r.target_yield.toFixed(0)}g
              <span className="ml-1.5 text-copper font-medium">×{r.scale_factor.toFixed(2)}</span>
            </span>
          </div>

          {/* Ingredient table */}
          <table className="w-full text-xs border-collapse bg-white">
            <thead>
              <tr className="border-b border-stone/50">
                <th className="text-left px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium w-1/2">
                  Ingredient
                </th>
                <th className="text-right px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium">
                  Original (g)
                </th>
                <th className="text-right px-4 py-2 text-[9px] text-copper uppercase tracking-[0.15em] font-bold bg-copper/5">
                  Scaled (g)
                </th>
              </tr>
            </thead>
            <tbody>
              {r.scaled_ingredients.map((ing, ii) => (
                <tr
                  key={ii}
                  className={`border-b border-stone/30 last:border-0 ${
                    ing.non_linear_warning ? 'bg-gold/5' : ''
                  }`}
                >
                  <td className={`px-4 py-2.5 font-light ${ing.non_linear_warning ? 'text-gold font-medium' : 'text-ink-muted'}`}>
                    {ing.name}
                    {ing.non_linear_warning && (
                      <span className="ml-1.5 text-[8px] text-gold/80 font-medium uppercase tracking-widest">adjusted</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-ink-faint font-light tabular-nums">
                    {ing.original_qty_g.toFixed(1)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-bold tabular-nums bg-copper/5 ${
                    ing.non_linear_warning ? 'text-gold' : 'text-copper-dark'
                  }`}>
                    {ing.scaled_qty_g.toFixed(1)}
                  </td>
                </tr>
              ))}
              {/* Total row */}
              <tr className="border-t-2 border-copper/30 bg-copper/10">
                <td className="px-4 py-2.5 font-semibold text-ink text-xs uppercase tracking-wide">Total</td>
                <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-ink-muted text-xs">
                  {r.scaled_ingredients.reduce((s, i) => s + i.original_qty_g, 0).toFixed(1)}
                </td>
                <td className="px-4 py-2.5 text-right font-bold tabular-nums text-copper text-xs bg-copper/5">
                  {r.scaled_ingredients.reduce((s, i) => s + i.scaled_qty_g, 0).toFixed(1)}
                </td>
              </tr>
            </tbody>
          </table>

        </div>
      ))}
    </div>
  )
}
