interface Props {
  steps: string[]
  done: boolean
}

const STEP_LABELS: Record<string, string> = {
  'classifying…':                               'Reading your request…',
  'searching knowledge base…':                  'Flipping through recipe books…',
  'scaling recipe…':                            'Weighing out the ingredients…',
  'consolidating ingredients…':                 'Prepping the mise en place…',
  'checking ratios…':                           'Tasting and adjusting ratios…',
}

const HIDDEN = /^intent:/i

function label(step: string) {
  return STEP_LABELS[step.toLowerCase()] ?? step
}

export default function StatusSteps({ steps, done }: Props) {
  const visible_steps = steps.filter(s => !HIDDEN.test(s.trim()))
  if (visible_steps.length === 0) return null

  const visible = done ? visible_steps : visible_steps.slice(-1)

  return (
    <div className="flex flex-col gap-1 mb-3">
      {visible.map((step, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-ink-faint">
          {!done && i === visible.length - 1 ? (
            <span className="flex gap-0.5">
              {[0, 1, 2].map(d => (
                <span
                  key={d}
                  className="w-1 h-1 rounded-full bg-copper/40 animate-pulse-dot"
                  style={{ animationDelay: `${d * 0.16}s` }}
                />
              ))}
            </span>
          ) : (
            <span className="text-copper/60">✓</span>
          )}
          <span>{label(step)}</span>
        </div>
      ))}
    </div>
  )
}
