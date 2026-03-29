import type { Document } from '../lib/api'

interface Props {
  status: Document['status']
}

export function StatusBadge({ status }: Props) {
  if (status === 'processing') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 border border-[#e5e5e5] bg-white">
        <span className="w-1.5 h-1.5 bg-[#22c55e] animate-pulse-dot inline-block" />
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#22c55e]">Scannen</span>
      </span>
    )
  }

  if (status === 'ready') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 border border-[#1a1a1a] bg-[#1a1a1a]">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2 5.5l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/>
        </svg>
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white">Gesichert</span>
      </span>
    )
  }

  if (status === 'nuked') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 border border-[#ef4444] bg-[#ef4444]">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2.5 2.5l5 5M7.5 2.5l-5 5" stroke="white" strokeWidth="1.5" strokeLinecap="square"/>
        </svg>
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white">Terminiert</span>
      </span>
    )
  }

  if (status === 'expired') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 border border-[#e5e5e5] bg-[#fcfcfc]">
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#999]">Abgelaufen</span>
      </span>
    )
  }

  // failed
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-1 border border-[#e5e5e5] bg-[#fcfcfc]">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#999]">Fehler</span>
    </span>
  )
}
