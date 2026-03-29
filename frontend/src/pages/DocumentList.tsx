import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { Document } from '../lib/api'
import { Upload } from '../components/Upload'
import { DocumentCard } from '../components/DocumentCard'

export function DocumentList() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const docs = await api.listDocuments()
      setDocuments(docs)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const hasProcessing = documents.some(d => d.status === 'processing')
    if (!hasProcessing) return
    const interval = setInterval(refresh, 3000)
    return () => clearInterval(interval)
  }, [documents, refresh])

  return (
    <div>
      <Upload onUploaded={refresh} />

      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#999]">
          Dokumente
          {documents.length > 0 && (
            <span className="ml-2 font-mono text-[#1a1a1a]">{documents.length}</span>
          )}
        </h2>
        <button
          onClick={refresh}
          className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-[#bbb] hover:text-[#1a1a1a] transition-colors"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          Aktualisieren
        </button>
      </div>

      {loading && (
        <div className="border border-[#e5e5e5] bg-white p-10 text-center">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#bbb]">
            Laden...
          </p>
        </div>
      )}

      {error && (
        <div className="border border-[#ef4444] bg-[#fff5f5] p-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#ef4444]">{error}</p>
        </div>
      )}

      {!loading && !error && documents.length === 0 && (
        <div className="border border-dashed border-[#e5e5e5] bg-white p-12 text-center">
          <div className="w-8 h-8 border border-[#e5e5e5] flex items-center justify-center mx-auto mb-3">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ccc" strokeWidth="2" strokeLinecap="square">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#bbb]">
            Keine Dokumente vorhanden
          </p>
          <p className="text-[11px] font-mono text-[#ccc] mt-1">
            Datei hochladen um zu beginnen
          </p>
        </div>
      )}

      {!loading && documents.length > 0 && (
        <div className="flex flex-col gap-px bg-[#e5e5e5] border border-[#e5e5e5]">
          {documents.map(doc => (
            <DocumentCard key={doc.id} doc={doc} />
          ))}
        </div>
      )}
    </div>
  )
}
