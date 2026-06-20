import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { scanUrl, scanFile } from '../utils/api'

const TABS = [
  { id: 'url', label: 'URL Scan', icon: '🌐' },
  { id: 'file', label: 'File Upload', icon: '📄' },
]

export default function ScannerPage() {
  const [activeTab, setActiveTab] = useState('url')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)
  const navigate = useNavigate()

  const handleUrlScan = async (e) => {
    e.preventDefault()
    if (!url.trim()) return setError('Please enter a URL')
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      return setError('URL must start with http:// or https://')
    }
    setError(null)
    setLoading(true)
    try {
      const result = await scanUrl(url)
      navigate(`/scan/results/${result.id}`)
    } catch (err) {
      setError(err.userMessage || 'Scan failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleFileScan = async (e) => {
    e.preventDefault()
    if (!file) return setError('Please select an HTML file')
    setError(null)
    setLoading(true)
    try {
      const result = await scanFile(file)
      navigate(`/scan/results/${result.id}`)
    } catch (err) {
      setError(err.userMessage || 'Scan failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleFileChange = (e) => {
    const selected = e.target.files?.[0]
    if (selected) {
      const ext = selected.name.split('.').pop().toLowerCase()
      if (!['html', 'htm'].includes(ext)) {
        setError('Only .html and .htm files are accepted')
        return
      }
      if (selected.size > 2 * 1024 * 1024) {
        setError('File size must be under 2MB')
        return
      }
      setFile(selected)
      setError(null)
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <h1 className="text-4xl sm:text-5xl font-bold mb-4">
          <span className="gradient-text">ShadowScan</span>
        </h1>
        <p className="text-lg text-text-secondary max-w-2xl mx-auto leading-relaxed">
          Detect prompt injection threats hidden in webpages before they reach your AI systems.
          Scan a URL or upload an HTML file for instant analysis.
        </p>
      </div>

      {/* Scanner Card */}
      <div className="max-w-2xl mx-auto">
        <div className="glass rounded-2xl p-6 sm:p-8 shadow-xl" style={{ animation: 'pulse-glow 4s ease-in-out infinite' }}>
          {/* Tab Switcher */}
          <div className="flex bg-bg-primary rounded-xl p-1 mb-6">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                onClick={() => { setActiveTab(tab.id); setError(null) }}
                className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all duration-300 flex items-center justify-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-gradient-to-r from-accent-cyan/20 to-accent-blue/20 text-accent-cyan shadow-md'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                <span>{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>

          {/* URL Scan Form */}
          {activeTab === 'url' && (
            <form onSubmit={handleUrlScan} className="animate-fade-in">
              <label htmlFor="url-input" className="block text-sm font-medium text-text-secondary mb-2">
                Target URL
              </label>
              <div className="flex gap-3">
                <input
                  id="url-input"
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/page-to-scan"
                  className="flex-1 bg-bg-primary border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan/50 transition-all"
                  disabled={loading}
                />
                <button
                  type="submit"
                  id="scan-url-btn"
                  disabled={loading || !url.trim()}
                  className="px-6 py-3 bg-gradient-to-r from-accent-cyan to-accent-blue text-bg-primary font-semibold rounded-xl hover:opacity-90 transition-all disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Scanning...
                    </span>
                  ) : 'Scan URL'}
                </button>
              </div>
            </form>
          )}

          {/* File Upload Form */}
          {activeTab === 'file' && (
            <form onSubmit={handleFileScan} className="animate-fade-in">
              <label htmlFor="file-input" className="block text-sm font-medium text-text-secondary mb-2">
                HTML File
              </label>
              <div
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  file
                    ? 'border-accent-cyan/50 bg-accent-cyan/5'
                    : 'border-border hover:border-text-muted'
                }`}
              >
                <input
                  ref={fileInputRef}
                  id="file-input"
                  type="file"
                  accept=".html,.htm"
                  onChange={handleFileChange}
                  className="hidden"
                  disabled={loading}
                />
                {file ? (
                  <div>
                    <p className="text-accent-cyan font-medium text-lg">📄 {file.name}</p>
                    <p className="text-text-muted text-sm mt-1">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-3xl mb-2">📁</p>
                    <p className="text-text-secondary font-medium">Click to select an HTML file</p>
                    <p className="text-text-muted text-sm mt-1">.html or .htm, max 2MB</p>
                  </div>
                )}
              </div>
              <button
                type="submit"
                id="scan-file-btn"
                disabled={loading || !file}
                className="w-full mt-4 px-6 py-3 bg-gradient-to-r from-accent-cyan to-accent-blue text-bg-primary font-semibold rounded-xl hover:opacity-90 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Scanning...
                  </span>
                ) : 'Scan File'}
              </button>
            </form>
          )}

          {/* Error Message */}
          {error && (
            <div id="scan-error" className="mt-4 p-3 bg-severity-high/10 border border-severity-high/30 rounded-xl text-severity-high text-sm animate-fade-in">
              ⚠️ {error}
            </div>
          )}
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-8">
          {[
            { icon: '🛡️', title: '13 Sources', desc: 'Extracts from comments, meta tags, alt text, ARIA, and more' },
            { icon: '🎯', title: '7 Categories', desc: 'Detects overrides, exfiltration, stealth, and chained payloads' },
            { icon: '📊', title: 'Risk Scoring', desc: 'Deterministic 0-100 score with severity classification' },
          ].map((card, i) => (
            <div key={i} className="glass rounded-xl p-4 text-center hover:border-accent-cyan/30 transition-all duration-300" style={{ animationDelay: `${i * 100}ms` }}>
              <div className="text-2xl mb-2">{card.icon}</div>
              <h3 className="font-semibold text-sm text-text-primary">{card.title}</h3>
              <p className="text-xs text-text-muted mt-1">{card.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
