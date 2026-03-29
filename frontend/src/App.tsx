import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom'
import { DocumentList } from './pages/DocumentList'
import { DocumentDetail } from './pages/DocumentDetail'

function ShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 2L4 7v9c0 6.627 5.148 11.956 12 13 6.852-1.044 12-6.373 12-13V7L16 2z" fill="white"/>
      <path d="M13 16.5l2.5 2.5 5-5" stroke="#1a1a1a" strokeWidth="2.5" strokeLinecap="square" strokeLinejoin="miter" fill="none"/>
    </svg>
  )
}

function Navbar() {
  return (
    <header className="border-b border-[#e5e5e5] bg-white sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-6 py-3">
        <Link to="/" className="inline-flex items-center gap-3 hover:opacity-70 transition-opacity">
          <div className="w-8 h-8 bg-[#1a1a1a] flex items-center justify-center">
            <ShieldIcon />
          </div>
          <span className="text-[13px] font-bold uppercase tracking-[0.2em] text-[#1a1a1a]">
            Shield
          </span>
        </Link>
      </div>
    </header>
  )
}

function Footer() {
  return (
    <footer className="border-t border-[#e5e5e5] mt-16">
      <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#bbb]">
          Shield
        </span>
        <div className="flex items-center gap-6">
          <a
            href="https://github.com/enki-run/shield"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#bbb] hover:text-[#1a1a1a] transition-colors"
          >
            GitHub
          </a>
          <span className="text-[11px] font-bold uppercase tracking-[0.15em] text-[#bbb]">
            AES-256-GCM
          </span>
        </div>
      </div>
    </footer>
  )
}

function AppContent() {
  return (
    <div className="min-h-screen bg-[#fcfcfc] flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-10">
        <Routes>
          <Route path="/" element={<DocumentList />} />
          <Route path="/documents/:id" element={<DocumentDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <Footer />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <AppContent />
    </BrowserRouter>
  )
}
