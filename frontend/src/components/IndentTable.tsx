import type { IndentSheet } from '../types'

interface Props {
  sheet: IndentSheet
}

export default function IndentTable({ sheet }: Props) {
  const grouped: Record<string, typeof sheet.rows> = {}
  for (const row of sheet.rows) {
    if (!grouped[row.category]) grouped[row.category] = []
    grouped[row.category].push(row)
  }

  return (
    <div className="mt-3 rounded-xl border border-stone bg-white overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-stone bg-linen flex items-baseline gap-3">
        <span className="font-serif text-ink font-medium">Indent Sheet</span>
        <span className="text-xs text-ink-faint truncate">{sheet.recipes.join(', ')}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone">
              <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-ink-faint font-medium">Ingredient</th>
              <th className="text-right px-4 py-2 text-[10px] uppercase tracking-wider text-ink-faint font-medium">Qty (g)</th>
              <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-ink-faint font-medium hidden sm:table-cell">Recipes</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(grouped).map(([category, rows]) => (
              <>
                <tr key={`cat-${category}`} className="bg-linen/60">
                  <td colSpan={3} className="px-4 py-1.5 text-[10px] font-semibold text-copper uppercase tracking-widest">
                    {category}
                  </td>
                </tr>
                {rows.map((row, i) => (
                  <tr key={`${category}-${i}`} className="border-t border-stone/30 hover:bg-parchment/60 transition-colors">
                    <td className="px-4 py-2 text-ink-muted capitalize">{row.ingredient}</td>
                    <td className="px-4 py-2 text-right text-ink font-medium tabular-nums">{row.total_qty_g.toFixed(0)}</td>
                    <td className="px-4 py-2 text-xs text-ink-faint hidden sm:table-cell">{row.sources.join(', ')}</td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-stone bg-linen/40">
              <td className="px-4 py-2 text-[10px] text-ink-faint font-medium uppercase tracking-wide">
                {sheet.rows.length} items
              </td>
              <td className="px-4 py-2 text-right text-ink font-medium tabular-nums">
                {sheet.rows.reduce((s, r) => s + r.total_qty_g, 0).toFixed(0)} g
              </td>
              <td className="hidden sm:table-cell" />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}
