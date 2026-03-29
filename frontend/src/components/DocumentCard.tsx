import { Link } from 'react-router-dom'
import type { Document } from '../lib/api'
import { StatusBadge } from './StatusBadge'

interface Props {
  doc: Document
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

export function DocumentCard({ doc }: Props) {
  const isNuked = doc.status === 'nuked'

  return (
    <Link
      to={`/documents/${doc.id}`}
      className={`group block border p-4 bg-white hover:bg-[#fafafa] transition-colors ${
        isNuked
          ? 'border-[#ef4444]'
          : 'border-[#e5e5e5] hover:border-[#ccc]'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          {/* File icon box */}
          <div className="w-8 h-8 border border-[#e5e5e5] flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2" strokeLinecap="square">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div className="min-w-0">
            <p className="font-mono text-[13px] font-medium text-[#1a1a1a] truncate leading-tight">
              {doc.filename}
            </p>
            <p className="font-mono text-[10px] text-[#bbb] mt-0.5">
              {doc.id.slice(0, 8)}...
            </p>
          </div>
        </div>
        <StatusBadge status={doc.status} />
      </div>

      <div className="mt-3 ml-11 flex items-center gap-5 flex-wrap">
        <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#bbb]">
          <span className="text-[#999]">{doc.mode}</span>
        </span>
        <span className="text-[10px] font-mono text-[#999]">
          <span className="font-bold text-[#1a1a1a]">{doc.entity_count}</span> Entitäten
        </span>
        <span className="text-[10px] font-mono text-[#999]">
          <span className="font-bold text-[#1a1a1a]">{doc.download_count}</span>/{doc.max_downloads} Downloads
        </span>
        <span className="text-[10px] font-mono text-[#bbb]">
          Ablauf: {formatDate(doc.expires_at)}
        </span>
      </div>
    </Link>
  )
}
