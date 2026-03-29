interface Props {
  report: { entity_type: string; count: number }[]
}

export function PiiReport({ report }: Props) {
  if (!report || report.length === 0) {
    return (
      <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#bbb]">
        Keine PII gefunden.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-px bg-[#e5e5e5] border border-[#e5e5e5]">
      {report.map(item => (
        <div key={item.entity_type} className="bg-white p-4">
          <div className="font-mono text-3xl font-bold text-[#1a1a1a] leading-none mb-1">
            {item.count}
          </div>
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#999]">
            {item.entity_type}
          </div>
        </div>
      ))}
    </div>
  )
}
