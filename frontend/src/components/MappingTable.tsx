import type { Mapping } from '../lib/api'
import { api } from '../lib/api'

interface Props {
  docId: string
  mappings: Mapping[]
}

export function MappingTable({ docId, mappings }: Props) {
  if (!mappings || mappings.length === 0) {
    return (
      <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#bbb]">
        Keine Mappings verfügbar.
      </p>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#999]">
          {mappings.length} Einträge
        </span>
        <a
          href={api.getMappingCsvUrl(docId)}
          download
          className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-[#1a1a1a] text-[10px] font-bold uppercase tracking-[0.15em] text-[#1a1a1a] hover:bg-[#1a1a1a] hover:text-white transition-colors"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          CSV herunterladen
        </a>
      </div>

      <div className="border border-[#e5e5e5] overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#e5e5e5] bg-[#fcfcfc]">
              <th className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-[0.2em] text-[#999]">
                Pseudonym
              </th>
              <th className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-[0.2em] text-[#999]">
                Original
              </th>
              <th className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-[0.2em] text-[#999]">
                Typ
              </th>
            </tr>
          </thead>
          <tbody>
            {mappings.map((m, i) => (
              <tr
                key={i}
                className={`hover:bg-[#fafafa] transition-colors ${i < mappings.length - 1 ? 'border-b border-[#f0f0f0]' : ''}`}
              >
                <td className="px-4 py-2.5 font-mono text-[12px] text-[#1a1a1a] whitespace-nowrap">
                  {m.pseudonym}
                </td>
                <td className="px-4 py-2.5 font-mono text-[12px] text-[#666] whitespace-nowrap">
                  {m.original_value}
                </td>
                <td className="px-4 py-2.5 whitespace-nowrap">
                  <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#999]">
                    {m.entity_type}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
