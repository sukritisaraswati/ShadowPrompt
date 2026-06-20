import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getScanResult, generateReport } from '../utils/api'

const SEVERITY_COLORS = {
  Clean: { ring: '#06d6a0', bg: 'rgba(6,214,160,0.1)', text: 'text-severity-clean' },
  Low: { ring: '#ffd166', bg: 'rgba(255,209,102,0.1)', text: 'text-severity-low' },
  Medium: { ring: '#f77f00', bg: 'rgba(247,127,0,0.1)', text: 'text-severity-medium' },
  High: { ring: '#ef476f', bg: 'rgba(239,71,111,0.1)', text: 'text-severity-high' },
  Critical: { ring: '#d62828', bg: 'rgba(214,40,40,0.1)', text: 'text-severity-critical' },
}

function ScoreGauge({ score, severity }) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const color = SEVERITY_COLORS[severity] || SEVERITY_COLORS.Clean
  const circumference = 2 * Math.PI * 54
  const offset = circumference - (animatedScore / 100) * circumference

  useEffect(() => {
    let frame
    const start = performance.now()
    const duration = 1200
    const animate = (now) => {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedScore(Math.round(score * eased))
      if (progress < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [score])

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="54" fill="none" stroke="currentColor" strokeWidth="8" className="text-bg-card" />
          <circle cx="60" cy="60" r="54" fill="none" stroke={color.ring} strokeWidth="8"
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round" style={{ transition: 'stroke-dashoffset 1.2s ease-out' }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold" style={{ color: color.ring }}>{animatedScore}</span>
          <span className="text-xs text-text-muted">/ 100</span>
        </div>
      </div>
      <span className={`mt-3 px-4 py-1.5 rounded-full text-sm font-semibold uppercase tracking-wider ${color.text}`}
        style={{ background: color.bg }}>
        {severity}
      </span>
    </div>
  )
}

function SeverityBadge({ severity }) {
  const color = SEVERITY_COLORS[severity] || SEVERITY_COLORS.Clean
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${color.text}`}
      style={{ background: color.bg }}>
      {severity}
    </span>
  )
}

function FindingCard({ finding, index }) {
  const [expanded, setExpanded] = useState(false)
  const categoryColors = {
    'Instruction Override': 'border-severity-high',
    'Data Exfiltration': 'border-severity-critical',
    'Unauthorized Action': 'border-severity-high',
    'Persona/Role Override': 'border-severity-medium',
    'Stealth Instruction': 'border-severity-medium',
    'Context Injection': 'border-severity-high',
    'Chained Payload Setup': 'border-severity-low',
  }
  const borderColor = categoryColors[finding.matched_category] || 'border-accent-blue'

  return (
    <div className={`bg-bg-card rounded-xl border-l-4 ${borderColor} overflow-hidden transition-all duration-300 animate-slide-up`}
      style={{ animationDelay: `${index * 80}ms` }}>
      <button id={`finding-${finding.id}`} onClick={() => setExpanded(!expanded)}
        className="w-full p-4 text-left flex items-start justify-between gap-4 hover:bg-bg-card-hover transition-colors">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-semibold text-accent-cyan">{finding.matched_category}</span>
            <span className="text-xs px-2 py-0.5 rounded-md bg-accent-blue/10 text-accent-blue font-medium">
              {finding.source_location}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-md bg-accent-purple/10 text-accent-purple font-medium">
              +{finding.risk_weight}
            </span>
          </div>
          <p className="text-sm text-text-secondary truncate">Rule: "{finding.matched_rule}"</p>
        </div>
        <svg className={`w-5 h-5 text-text-muted transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 animate-fade-in">
          <div>
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1">Evidence</p>
            <pre className="bg-bg-primary rounded-lg p-3 text-xs text-severity-medium font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto border border-border">
              {finding.evidence_text}
            </pre>
          </div>
          <div className="p-3 rounded-lg bg-severity-high/5 border border-severity-high/20">
            <p className="text-xs font-semibold text-severity-high mb-1">⚠ Impact</p>
            <p className="text-sm text-text-secondary">{finding.impact}</p>
          </div>
          <div className="p-3 rounded-lg bg-severity-clean/5 border border-severity-clean/20">
            <p className="text-xs font-semibold text-severity-clean mb-1">✅ Remediation</p>
            <p className="text-sm text-text-secondary">{finding.remediation}</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ResultsPage() {
  const { id } = useParams()
  const [scan, setScan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    loadResult()
  }, [id])

  const loadResult = async () => {
    try {
      const data = await getScanResult(id)
      setScan(data)
    } catch (err) {
      setError(err.userMessage || 'Failed to load scan results')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await generateReport(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `shadowscan_report_${id.slice(0, 8)}.html`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Failed to generate report')
    } finally {
      setExporting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-12 h-12 border-4 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-24">
        <p className="text-severity-high text-lg mb-4">⚠️ {error}</p>
        <Link to="/scan" className="text-accent-cyan hover:underline">← Back to Scanner</Link>
      </div>
    )
  }

  const categories = [...new Set(scan.findings.map(f => f.matched_category))]
  const filteredFindings = filter === 'all'
    ? scan.findings
    : scan.findings.filter(f => f.matched_category === filter)

  return (
    <div className="animate-fade-in max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <Link to="/scan" className="text-sm text-text-muted hover:text-accent-cyan transition-colors">
          ← Back to Scanner
        </Link>
        <button id="export-btn" onClick={handleExport} disabled={exporting}
          className="px-4 py-2 bg-bg-card border border-border rounded-lg text-sm font-medium text-text-secondary hover:text-accent-cyan hover:border-accent-cyan/50 transition-all disabled:opacity-40">
          {exporting ? 'Generating...' : '📥 Export Report'}
        </button>
      </div>

      {/* Score Section */}
      <div className="glass rounded-2xl p-8 mb-6 text-center">
        <p className="text-text-muted text-sm mb-1">Scan Target</p>
        <h1 className="text-lg font-semibold text-accent-blue mb-6 break-all">
          {scan.target_url || scan.target_filename || 'Unknown'}
        </h1>
        <ScoreGauge score={scan.score} severity={scan.severity} />
        <div className="flex items-center justify-center gap-6 mt-6 text-sm text-text-secondary">
          <span>{scan.finding_count} finding{scan.finding_count !== 1 ? 's' : ''}</span>
          <span>•</span>
          <span>{scan.scan_type.toUpperCase()} scan</span>
          <span>•</span>
          <span>{new Date(scan.created_at).toLocaleString()}</span>
        </div>
      </div>

      {/* No Findings Message */}
      {scan.finding_count === 0 && (
        <div className="glass rounded-2xl p-8 text-center">
          <p className="text-3xl mb-3">✅</p>
          <h2 className="text-lg font-semibold text-severity-clean mb-2">No Suspicious Patterns Detected</h2>
          <p className="text-text-secondary text-sm max-w-md mx-auto">
            No configured prompt injection patterns were found. This does not guarantee the page is safe — it means no known patterns matched the current rule set.
          </p>
        </div>
      )}

      {/* Findings */}
      {scan.finding_count > 0 && (
        <>
          {/* Category Filter */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <button onClick={() => setFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filter === 'all' ? 'bg-accent-cyan/15 text-accent-cyan' : 'bg-bg-card text-text-muted hover:text-text-secondary'
              }`}>
              All ({scan.findings.length})
            </button>
            {categories.map(cat => (
              <button key={cat} onClick={() => setFilter(cat)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  filter === cat ? 'bg-accent-cyan/15 text-accent-cyan' : 'bg-bg-card text-text-muted hover:text-text-secondary'
                }`}>
                {cat} ({scan.findings.filter(f => f.matched_category === cat).length})
              </button>
            ))}
          </div>

          {/* Findings List */}
          <div className="space-y-3">
            {filteredFindings.map((finding, i) => (
              <FindingCard key={finding.id} finding={finding} index={i} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
