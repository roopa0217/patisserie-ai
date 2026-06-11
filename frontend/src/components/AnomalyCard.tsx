import type { AnomalyReport } from '../types/index'

interface Props {
  report: AnomalyReport
}

export default function AnomalyCard({ report }: Props) {
  const pass = report.overall_pass
  const checked = report.results.filter(r => r.min_g > 0 || r.max_g > 0)

  return (
    <div className="mt-3 rounded-xl border border-stone overflow-hidden">

      {/* Header */}
      <div className="px-4 py-2.5 bg-linen border-b border-stone flex items-center justify-between gap-2">
        <span className="font-serif text-sm text-ink font-medium">{report.recipe_name}</span>
        <span className={`text-[10px] font-semibold uppercase tracking-widest ${pass ? 'text-pass-green' : 'text-fail-red'}`}>
          {pass ? '✓ Pass' : '✗ Fail'}
        </span>
      </div>

      {checked.length === 0 ? (
        <p className="px-4 py-3 text-sm text-ink-faint bg-white font-light">
          No threshold-checked ingredients found.
        </p>
      ) : (
        <table className="w-full text-xs border-collapse bg-white">
          <thead>
            <tr className="border-b border-stone/50">
              <th className="text-left px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium">Ingredient</th>
              <th className="text-left px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium">Component</th>
              <th className="text-right px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium">Qty (g)</th>
              <th className="text-right px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium">Limit (g)</th>
              <th className="text-right px-4 py-2 text-[9px] text-ink-faint uppercase tracking-[0.15em] font-medium w-12"></th>
            </tr>
          </thead>
          <tbody>
            {report.results.map((r, i) => (
              <>
                <tr
                  key={i}
                  className={`border-b border-stone/30 last:border-0 ${!r.passed ? 'bg-fail-red/4' : ''}`}
                >
                  <td className={`px-4 py-2.5 font-medium ${!r.passed ? 'text-fail-red' : 'text-ink'}`}>
                    {r.ingredient}
                  </td>
                  <td className="px-4 py-2.5 text-ink-faint font-light">{r.component}</td>
                  <td className={`px-4 py-2.5 text-right font-medium tabular-nums ${!r.passed ? 'text-fail-red' : 'text-ink'}`}>
                    {r.actual_g.toFixed(1)}
                  </td>
                  <td className="px-4 py-2.5 text-right text-ink-faint font-light tabular-nums">
                    {r.min_g > 0 ? `${r.min_g}–` : '≤'}{r.max_g}
                  </td>
                  <td className={`px-4 py-2.5 text-right text-[9px] font-semibold uppercase tracking-wide ${r.passed ? 'text-pass-green' : 'text-fail-red'}`}>
                    {r.passed ? '✓' : '✗'}
                  </td>
                </tr>
                {!r.passed && r.advice && (
                  <tr key={`${i}-advice`} className="border-b border-stone/30">
                    <td colSpan={5} className="px-4 pb-2.5 pt-0">
                      <p className="text-[11px] text-fail-red/70 font-light leading-relaxed bg-fail-red/4 rounded-lg px-3 py-2 border border-fail-red/15">
                        {r.advice}
                      </p>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
