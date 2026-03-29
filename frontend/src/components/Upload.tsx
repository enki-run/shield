import { useCallback, useState } from 'react'
import { api } from '../lib/api'

interface Props {
  onUploaded: () => void
}

export function Upload({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false)
  const [mode, setMode] = useState<'balanced' | 'compliant'>('balanced')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFile = useCallback(async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      await api.uploadDocument(file, mode)
      onUploaded()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload fehlgeschlagen')
    } finally {
      setUploading(false)
    }
  }, [mode, onUploaded])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  const onInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }, [handleFile])

  return (
    <div className="mb-10">
      {/* Upload area */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`relative border-2 border-dashed p-12 text-center transition-colors ${
          dragging
            ? 'border-[#1a1a1a] bg-[#f5f5f5]'
            : 'border-[#e5e5e5] hover:border-[#ccc] bg-white'
        }`}
      >
        {/* Decorative corner marks */}
        <span className="absolute top-2 left-2 w-3 h-3 border-t-2 border-l-2 border-[#1a1a1a] opacity-40" />
        <span className="absolute top-2 right-2 w-3 h-3 border-t-2 border-r-2 border-[#1a1a1a] opacity-40" />
        <span className="absolute bottom-2 left-2 w-3 h-3 border-b-2 border-l-2 border-[#1a1a1a] opacity-40" />
        <span className="absolute bottom-2 right-2 w-3 h-3 border-b-2 border-r-2 border-[#1a1a1a] opacity-40" />

        {/* Icon */}
        <div className="w-10 h-10 border border-[#e5e5e5] flex items-center justify-center mx-auto mb-4">
          {uploading ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="animate-spin text-[#1a1a1a]">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeOpacity="0.2"/>
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="2" strokeLinecap="square"/>
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1a1a1a" strokeWidth="2" strokeLinecap="square" strokeLinejoin="miter">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          )}
        </div>

        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#999] mb-1">
          {uploading ? 'Wird verarbeitet...' : 'Datei ablegen oder auswählen'}
        </p>
        <p className="text-[11px] text-[#bbb] font-mono mb-6">
          .txt .md .pdf .docx .xlsx .csv .json
        </p>

        {/* Mode selector + upload button */}
        <div className="flex items-center justify-center gap-3 flex-wrap">
          <div className="flex items-center border border-[#e5e5e5]">
            <button
              onClick={() => setMode('balanced')}
              disabled={uploading}
              className={`px-3 py-2 text-[11px] font-bold uppercase tracking-[0.15em] transition-colors ${
                mode === 'balanced'
                  ? 'bg-[#1a1a1a] text-white'
                  : 'bg-white text-[#999] hover:text-[#1a1a1a]'
              }`}
            >
              Balanced
            </button>
            <button
              onClick={() => setMode('compliant')}
              disabled={uploading}
              className={`px-3 py-2 text-[11px] font-bold uppercase tracking-[0.15em] transition-colors border-l border-[#e5e5e5] ${
                mode === 'compliant'
                  ? 'bg-[#1a1a1a] text-white'
                  : 'bg-white text-[#999] hover:text-[#1a1a1a]'
              }`}
            >
              Compliant
            </button>
          </div>

          <label className={`inline-flex items-center gap-2 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.15em] border transition-colors ${
            uploading
              ? 'border-[#e5e5e5] text-[#bbb] cursor-not-allowed bg-[#fcfcfc]'
              : 'border-[#1a1a1a] text-white bg-[#1a1a1a] hover:bg-white hover:text-[#1a1a1a] cursor-pointer'
          }`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            {uploading ? 'Laden...' : 'Datei auswählen'}
            <input
              type="file"
              className="hidden"
              disabled={uploading}
              onChange={onInputChange}
              accept=".txt,.md,.pdf,.docx,.xlsx,.csv,.json"
            />
          </label>
        </div>

        {error && (
          <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.1em] text-[#ef4444]">{error}</p>
        )}
      </div>

      {/* Mode description */}
      <div className="mt-2 flex items-center gap-6 px-1">
        <span className="text-[10px] font-mono text-[#bbb]">
          {mode === 'balanced'
            ? 'balanced — ausgewogene Pseudonymisierung für Lesbarkeit'
            : 'compliant — maximale Anonymisierung für Compliance'}
        </span>
      </div>
    </div>
  )
}
