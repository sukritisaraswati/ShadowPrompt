import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listScanResults } from '../utils/api'

const SEVERITY_STYLES = {
  Clean: 'text-severity-clean bg-severity-clean/10',
  Low: 'text-severity-low bg-severity-low/10',
  Medium: 'text-severity-medium bg-severity-medium/10',
  High: 'text-severity-high bg-severity-high/10',
  Critical: 'text-severity-critical bg-severity-critical/10',
}

export default function HistoryPage() {
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    loadScans()
  }, [filter, page])

  const loadScans = async () => {
    setLoading(true)
    try {
      const data = await listScanResults(page, 20, filter)
      setScans(data)
    } catch {
      setScans([])
    } finally {
      setLoading(false)
    }
  }

  const severities = [null, 'Clean', 'Low', 'Medium', 'High', 'Critical']

  return (
    <div className="animate-fade-in">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold mb-3">
          📋 <span className="gradient-text">Scan History</span>
        </h1>
        <p className="text-text-secondary">View all past scans and their results.</p>
      </div>

      {/* Severity Filter */}
      <div className="flex items-center gap-2 mb-6 flex-wrap">
        {severities.map((sev) => (
          <button key={sev || 'all'} onClick={() => { setFilter(sev); setPage(1) }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filter === sev
                ? 'bg-accent-cyan/15 text-accent-cyan'
                : 'bg-bg-card text-text-muted hover:text-text-secondary border border-border'
            }`}>
            {sev || 'All'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-10 h-10 border-4 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin" />
        </div>
      ) : scans.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl">
          <p className="text-4xl mb-3">📭</p>
          <p className="text-text-muted text-lg mb-2">No scans yet</p>
          <Link to="/scan" className="text-accent-cyan hover:underline text-sm">Run your first scan →</Link>
        </div>
      ) : (
        <>
          <div className="glass rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Target</th>
                  <th className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Type</th>
                  <th className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider text-center">Score</th>
                  <th className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider text-center">Severity</th>
                  <th className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider text-center">Findings</th>
                  <th className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Date</th>
                </tr>
              </thead>
              <tbody>
                {scans.map((scan, i) => (
                  <tr key={scan.id} className="border-b border-border/50 hover:bg-bg-card-hover transition-colors animate-fade-in"
                    style={{ animationDelay: `${i * 40}ms` }}>
                    <td className="px-4 py-3">
                      <Link to={`/scan/results/${scan.id}`}
                        className="text-sm text-accent-blue hover:text-accent-cyan transition-colors truncate block max-w-xs">
                        {scan.target_url || scan.target_filename || 'Unknown'}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-md bg-bg-card text-text-muted font-medium uppercase">
                        {scan.scan_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className="text-sm font-bold text-text-primary">{scan.score}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${SEVERITY_STYLES[scan.severity] || ''}`}>
                        {scan.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-text-secondary">{scan.finding_count}</td>
                    <td className="px-4 py-3 text-xs text-text-muted">
                      {new Date(scan.created_at).toLocaleDateString()} {new Date(scan.created_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-center gap-3 mt-6">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="px-3 py-1.5 rounded-lg text-sm bg-bg-card border border-border text-text-muted hover:text-text-primary disabled:opacity-30 transition-all">
              ← Prev
            </button>
            <span className="text-sm text-text-muted">Page {page}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={scans.length < 20}
              className="px-3 py-1.5 rounded-lg text-sm bg-bg-card border border-border text-text-muted hover:text-text-primary disabled:opacity-30 transition-all">
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  )
}
