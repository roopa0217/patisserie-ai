interface Props {
  confidence: number
}

function colour(c: number) {
  if (c >= 0.7) return 'bg-pass-green'
  if (c >= 0.4) return 'bg-gold'
  return 'bg-fail-red'
}

function label(c: number) {
  if (c >= 0.7) return 'High confidence'
  if (c >= 0.4) return 'Medium confidence'
  return 'Low confidence'
}

export default function ConfidenceBar({ confidence }: Props) {
  const pct = Math.round(confidence * 100)
  return (
    <div className="mt-3 flex items-center gap-2">
      <div className="flex-1 h-0.5 bg-bark3 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colour(confidence)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-cream-muted whitespace-nowrap">
        {label(confidence)} · {pct}%
      </span>
    </div>
  )
}
