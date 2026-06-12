import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchStats, uploadPdf } from '../api/client'
import type { Stats } from '../types/index'

export default function UploadView() {
  const [stats, setStats] = useState<Stats>({ pinecone_vectors: 0, bm25_chunks: 0 })
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const loadStats = useCallback(async () => {
    try { setStats(await fetchStats()) } catch { /* offline */ }
  }, [])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  async function handleFile(file: File) {
    if (!file.name.endsWith('.pdf')) {
      setUploadMsg({ text: 'Only PDF files are accepted.', ok: false })
      return
    }
    setUploading(true)
    setUploadMsg(null)
    try {
      const result = await uploadPdf(file)
      setUploadMsg({ text: `Recipes ingested from "${file.name}".`, ok: true })
      await loadStats()
    } catch (e: unknown) {
      setUploadMsg({ text: (e as Error).message ?? 'Upload failed', ok: false })
    } finally {
      setUploading(false)
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-parchment px-8">
      <div className="w-full max-w-lg animate-fade-in">

        {/* Heading */}
        <div className="mb-8 text-center">
          <h2 className="font-serif text-2xl text-ink font-medium tracking-wide mb-2">
            Upload Recipe Books
          </h2>
          <p className="text-sm text-ink-faint font-light">
            Upload a PDF booklet — recipes are parsed and indexed automatically.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && fileRef.current?.click()}
          className={`
            rounded-2xl border-2 cursor-pointer
            flex flex-col items-center justify-center
            px-8 py-16 text-center transition-all duration-200
            ${uploading ? 'pointer-events-none opacity-50' : ''}
            ${dragging
              ? 'border-copper/50 bg-copper/4 scale-[1.01]'
              : 'border-stone border-dashed hover:border-copper/40 hover:bg-linen/40'
            }
          `}
        >
          {uploading ? (
            <>
              <div className="w-6 h-6 border border-stone-dark border-t-copper rounded-full animate-spin mb-4" />
              <p className="text-sm text-ink-muted font-light">Processing your PDF…</p>
              <p className="text-xs text-ink-faint mt-1 font-light">Embedding recipes into the knowledge base</p>
            </>
          ) : dragging ? (
            <>
              <div className="w-10 h-10 rounded-full bg-copper/10 flex items-center justify-center mb-4">
                <svg className="w-5 h-5 text-copper" fill="none" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.5">
                  <path strokeLinecap="round" d="M10 14V6m0 0L7 8.5M10 6l3 2.5" />
                </svg>
              </div>
              <p className="text-sm text-ink font-medium">Release to upload</p>
            </>
          ) : (
            <>
              <div className="w-10 h-10 rounded-full bg-linen flex items-center justify-center mb-4 border border-stone">
                <svg className="w-5 h-5 text-ink-faint" fill="none" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.5">
                  <path strokeLinecap="round" d="M10 14V6m0 0L7 8.5M10 6l3 2.5M4 16a2 2 0 002 2h8a2 2 0 002-2" />
                </svg>
              </div>
              <p className="text-sm text-ink font-light mb-1">Drop a PDF here</p>
              <p className="text-xs text-ink-faint font-light">or click to browse</p>
            </>
          )}
        </div>

        <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={onFileChange} />

        {/* Upload feedback */}
        {uploadMsg && (
          <div className={`mt-4 rounded-xl px-4 py-3 text-sm font-light border ${
            uploadMsg.ok
              ? 'bg-pass-green/5 border-pass-green/25 text-pass-green'
              : 'bg-fail-red/5 border-fail-red/25 text-fail-red'
          }`}>
            {uploadMsg.ok ? '✓ ' : '✗ '}{uploadMsg.text}
          </div>
        )}

        {/* Stats */}
        {stats.pinecone_vectors > 0 && (
          <div className="mt-6 rounded-xl border border-stone bg-sand px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-[9px] text-ink-faint uppercase tracking-[0.2em] font-medium mb-1">Knowledge Base</p>
              <p className="text-sm text-ink font-light">Recipes indexed</p>
            </div>
            <div className="w-8 h-8 rounded-full bg-linen border border-stone flex items-center justify-center">
              <svg className="w-4 h-4 text-ink-faint" fill="none" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" d="M9 12h6m-3-3v6M4 6a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
              </svg>
            </div>
          </div>
        )}

        {/* Hint */}
        <p className="text-[11px] text-ink-faint text-center mt-6 font-light leading-relaxed">
          PDF is parsed for recipe names, components, and ingredients.<br />
          Re-uploading the same file will update existing recipes.
        </p>
      </div>
    </div>
  )
}
