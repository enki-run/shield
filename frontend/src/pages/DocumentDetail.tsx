import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { DocumentDetail as DocDetail } from '../lib/api'
import { StatusBadge } from '../components/StatusBadge'
import { PiiReport } from '../components/PiiReport'
import { MappingTable } from '../components/MappingTable'
import { DownloadToken } from '../components/DownloadToken'

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

interface MetaItemProps {
  label: string
  value: string
  highlight?: boolean
}

function MetaItem({ label, value, highlight }: MetaItemProps) {
  return (
    <div className="border border-[#e5e5e5] p-3 bg-white">
      <dt className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#bbb] mb-1">{label}</dt>
      <dd className={`font-mono text-[12px] ${highlight ? 'text-[#ef4444]' : 'text-[#1a1a1a]'}`}>{value}</dd>
    </div>
  )
}

export function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const [doc, setDoc] = useState<DocDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    api.getDocument(id)
      .then(d => { setDoc(d); setLoading(false) })
      .catch(e => { setError(e instanceof Error ? e.message : 'Fehler'); setLoading(false) })
  }, [id])

  if (loading) {
    return (
      <div className="border border-[#e5e5e5] bg-white p-16 text-center">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#bbb]">Laden...</p>
      </div>
    )
  }

  if (error || !doc) {
    return (
      <div className="border border-[#ef4444] bg-[#fff5f5] p-10 text-center">
        <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#ef4444] mb-4">
          {error || 'Dokument nicht gefunden'}
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-[#1a1a1a] border border-[#1a1a1a] px-3 py-2 hover:bg-[#1a1a1a] hover:text-white transition-colors"
        >
          Zurück zur Liste
        </Link>
      </div>
    )
  }

  const isNuked = doc.status === 'nuked'
  const isReady = doc.status === 'ready'

  return (
    <div>
      {/* Back navigation */}
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-[#bbb] hover:text-[#1a1a1a] transition-colors mb-8"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        Zurück
      </Link>

      {/* Document header */}
      <div className={`border p-6 bg-white mb-1 ${isNuked ? 'border-[#ef4444]' : 'border-[#e5e5e5]'}`}>
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 border border-[#e5e5e5] flex items-center justify-center flex-shrink-0">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2" strokeLinecap="square">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div className="min-w-0">
              <h2 className="font-mono text-[15px] font-bold text-[#1a1a1a] truncate leading-tight">
                {doc.filename}
              </h2>
              <p className="font-mono text-[10px] text-[#bbb] mt-0.5">{doc.id}</p>
            </div>
          </div>
          <StatusBadge status={doc.status} />
        </div>

        {/* Metadata grid */}
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-px bg-[#e5e5e5]">
          <MetaItem label="Modus" value={doc.mode} />
          <MetaItem label="Format" value={`${doc.input_format} → ${doc.output_format}`} />
          <MetaItem label="Entitäten" value={String(doc.entity_count)} />
          <MetaItem label="Downloads" value={`${doc.download_count} / ${doc.max_downloads}`} />
          <MetaItem label="Erstellt" value={formatDate(doc.created_at)} />
          <MetaItem label="Läuft ab" value={formatDate(doc.expires_at)} />
          {doc.nuked_at && (
            <MetaItem label="Terminiert am" value={formatDate(doc.nuked_at)} highlight />
          )}
        </dl>
      </div>

      <div className="flex flex-col gap-1 mt-1">
        {/* PII Report */}
        <section className="border border-[#e5e5e5] bg-white p-6">
          <h3 className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#999] mb-4">
            PII-Bericht
          </h3>
          <PiiReport report={doc.pii_report} />
        </section>

        {/* Mapping Table */}
        <section className="border border-[#e5e5e5] bg-white p-6">
          <h3 className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#999] mb-4">
            Pseudonymisierungs-Mapping
          </h3>
          <MappingTable docId={doc.id} mappings={doc.mappings} />
        </section>

        {/* Download Token */}
        <section className="border border-[#e5e5e5] bg-white p-6">
          <h3 className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#999] mb-4">
            Einmal-Link erstellen
          </h3>
          <DownloadToken docId={doc.id} disabled={!isReady} />
        </section>
      </div>
    </div>
  )
}
