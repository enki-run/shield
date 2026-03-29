import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { TokenStatus } from '../lib/api'

interface Props {
  docId: string
  disabled: boolean
}

function formatCountdown(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function DownloadToken({ docId, disabled }: Props) {
  const [status, setStatus] = useState<TokenStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(0)
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.getTokenStatus(docId)
      setStatus(s)
      if (s.has_active_token && s.ttl_seconds) {
        setCountdown(s.ttl_seconds)
      }
    } catch {
      // Fehler ignorieren bei initialem Load
    }
  }, [docId])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    if (countdown > 0) {
      timerRef.current = setInterval(() => {
        setCountdown(c => {
          if (c <= 1) {
            clearInterval(timerRef.current!)
            setStatus(s => s ? { ...s, has_active_token: false } : s)
            return 0
          }
          return c - 1
        })
      }, 1000)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [countdown])

  const createToken = async () => {
    setLoading(true)
    setError(null)
    try {
      const info = await api.createToken(docId)
      setStatus({ has_active_token: true, url: info.url, expires_at: info.expires_at, ttl_seconds: info.ttl_seconds })
      setCountdown(info.ttl_seconds)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Erstellen')
    } finally {
      setLoading(false)
    }
  }

  const revokeToken = async () => {
    setLoading(true)
    setError(null)
    try {
      await api.revokeToken(docId)
      setStatus({ has_active_token: false })
      setCountdown(0)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Widerrufen')
    } finally {
      setLoading(false)
    }
  }

  const copyUrl = async () => {
    if (status?.url) {
      await navigator.clipboard.writeText(status.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (disabled) {
    return (
      <div className="border border-[#e5e5e5] p-4 bg-[#fcfcfc]">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#bbb]">
          Nur für Dokumente mit Status "Gesichert" verfügbar.
        </p>
      </div>
    )
  }

  return (
    <div>
      {error && (
        <div className="mb-3 border border-[#ef4444] bg-[#fff5f5] px-4 py-3">
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#ef4444]">{error}</p>
        </div>
      )}

      {!status?.has_active_token && (
        <button
          onClick={createToken}
          disabled={loading}
          className={`inline-flex items-center gap-2 px-5 py-3 border text-[11px] font-bold uppercase tracking-[0.2em] transition-colors ${
            loading
              ? 'border-[#e5e5e5] text-[#bbb] cursor-not-allowed bg-[#fcfcfc]'
              : 'border-[#1a1a1a] bg-[#1a1a1a] text-white hover:bg-white hover:text-[#1a1a1a]'
          }`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
            <rect x="3" y="11" width="18" height="11" rx="0"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          {loading ? 'Erstelle Link...' : 'Sicheren Link erstellen'}
        </button>
      )}

      {status?.has_active_token && status.url && (
        <div className="border border-[#e5e5e5]">
          {/* Token header — dark panel */}
          <div className="bg-[#1a1a1a] px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="square">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white">
                {formatCountdown(countdown)} Verbleibend
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-[#22c55e] animate-pulse-dot inline-block" />
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#22c55e]">Aktiv</span>
            </div>
          </div>

          {/* URL display */}
          <div className="px-4 py-3 border-b border-[#e5e5e5]">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#bbb] mb-1.5">
              Download-URL
            </p>
            <code className="block text-[11px] font-mono text-[#1a1a1a] break-all leading-relaxed">
              {status.url}
            </code>
          </div>

          {/* Actions */}
          <div className="px-4 py-3 flex items-center gap-2 bg-[#fcfcfc]">
            <button
              onClick={copyUrl}
              className="inline-flex items-center gap-1.5 px-3 py-2 border border-[#1a1a1a] text-[10px] font-bold uppercase tracking-[0.15em] text-[#1a1a1a] hover:bg-[#1a1a1a] hover:text-white transition-colors"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
                <rect x="9" y="9" width="13" height="13"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              {copied ? 'Kopiert!' : 'Kopieren'}
            </button>
            <button
              onClick={revokeToken}
              disabled={loading}
              className={`inline-flex items-center gap-1.5 px-3 py-2 border text-[10px] font-bold uppercase tracking-[0.15em] transition-colors ${
                loading
                  ? 'border-[#e5e5e5] text-[#bbb] cursor-not-allowed'
                  : 'border-[#ef4444] text-[#ef4444] hover:bg-[#ef4444] hover:text-white'
              }`}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
              {loading ? 'Laden...' : 'Widerrufen'}
            </button>
          </div>
        </div>
      )}

      {/* Active token exists but URL not available (page was reloaded) */}
      {status?.has_active_token && !status.url && (
        <div className="border border-[#e5e5e5]">
          <div className="bg-[#1a1a1a] px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="square">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white">
                {formatCountdown(countdown)} Verbleibend
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-[#f59e0b] animate-pulse-dot inline-block" />
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#f59e0b]">Ausstehend</span>
            </div>
          </div>

          <div className="px-4 py-3 border-b border-[#e5e5e5]">
            <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#888] leading-relaxed">
              Ein Einmal-Link wurde generiert und ist noch nicht abgerufen worden.
              Die URL kann aus Sicherheitsgründen nicht erneut angezeigt werden.
              Widerrufen Sie den Link, um einen neuen zu erstellen.
            </p>
          </div>

          <div className="px-4 py-3 bg-[#fcfcfc]">
            <button
              onClick={revokeToken}
              disabled={loading}
              className={`inline-flex items-center gap-1.5 px-3 py-2 border text-[10px] font-bold uppercase tracking-[0.15em] transition-colors ${
                loading
                  ? 'border-[#e5e5e5] text-[#bbb] cursor-not-allowed'
                  : 'border-[#ef4444] text-[#ef4444] hover:bg-[#ef4444] hover:text-white'
              }`}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
              {loading ? 'Laden...' : 'Link widerrufen & neuen erstellen'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
