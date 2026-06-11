import type { Source } from '../types'

interface Props {
  sources: Source[]
}

export default function Citations({ sources }: Props) {
  if (!sources || sources.length === 0) return null

  const files = [...new Set(sources.map(s => s.file).filter(Boolean))]
  if (files.length === 0) return null

  return (
    <div className="mt-3 pt-3 border-t border-stone">
      <p className="text-[10px] text-ink-faint uppercase tracking-[0.15em] mb-1">Source</p>
      {files.map((file, i) => (
        <p key={i} className="text-xs text-ink-faint truncate" title={file}>{file}</p>
      ))}
    </div>
  )
}
