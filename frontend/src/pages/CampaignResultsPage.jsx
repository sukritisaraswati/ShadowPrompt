import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getCampaign, generateLabReport } from '../utils/api'

const VERDICT_STYLES = {
  PASS: 'bg-severity-clean/15 text-severity-clean',
  FAIL: 'bg-severity-high/15 text-severity-high',
  PARTIAL: 'bg-severity-medium/15 text-severity-medium',
  UNCLEAR: 'bg-text-muted/15 text-text-muted',
}
const RATING_COLORS = {
  Secure: 'text-severity-clean',
  Moderate: 'text-severity-low',
  Vulnerable: 'text-severity-medium',
  Critical: 'text-severity-high',
}
const LEVEL_NAMES = { 1: 'Basic Jailbreaks', 2: 'Persona Manipulation', 3: 'Adversarial Design' }

export default function CampaignResultsPage() {
  const { id } = useParams()
  const [campaign, setCampaign] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState(null)
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => { loadCampaign() }, [id])

  const loadCampaign = async () => {
    try {
      const data = await getCampaign(id)
      setCampaign(data)
    } catch {
      setCampaign(null)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return (
    <div className="flex justify-center py-20">
      <div className="w-10 h-10 border-4 border-accent-purple/30 border-t-accent-purple rounded-full animate-spin" />
    </div>
  )

  if (!campaign) return (
    <div className="text-center py-20 glass rounded-2xl">
      <p className="text-text-muted text-lg">Campaign not found.</p>
      <Link to="/lab/connect" className="text-accent-purple hover:underline text-sm mt-2 inline-block">← Back to Lab</Link>
    </div>
  )

  const handleExport = async () => {
    try {
      const blob = await generateLabReport(id)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `shadowprompt_lab_report_${id.slice(0, 8)}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert('Failed to generate PDF. Make sure WeasyPrint and its dependencies are installed on the backend.')
    }
  }

  const filteredResults = filter
    ? campaign.test_results.filter(tr => tr.verdict === filter)
    : campaign.test_results

  return (
    <div className="animate-fade-in">
      <div className="flex justify-between items-center mb-8">
        <div className="flex-1"></div>
        <div className="text-center flex-1">
          <h1 className="text-3xl font-bold mb-2">
            📊 <span className="gradient-text">Campaign Results</span>
          </h1>
          <p className="text-text-secondary text-sm">
            {campaign.model_name} • {campaign.status === 'completed' ? 'Completed' : campaign.status}
          </p>
        </div>
        <div className="flex-1 flex justify-end">
          <button onClick={handleExport} className="btn-secondary text-sm flex items-center gap-2">
            📄 Export PDF
          </button>
        </div>
      </div>

      {/* Overall Score */}
      <div className="glass rounded-2xl p-8 text-center mb-6">
        <p className="text-sm text-text-muted mb-2">Overall Security Score</p>
        <div className="relative w-40 h-40 mx-auto mb-3">
          <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
            <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" strokeWidth="8"
              className="text-bg-card" />
            <circle cx="60" cy="60" r="50" fill="none" strokeWidth="8"
              strokeDasharray={`${(campaign.overall_score || 0) * 3.14} 314`}
              strokeLinecap="round"
              className={`${campaign.overall_score >= 90 ? 'text-severity-clean' : campaign.overall_score >= 70 ? 'text-severity-low' : campaign.overall_score >= 40 ? 'text-severity-medium' : 'text-severity-high'} transition-all duration-1000`}
              style={{ stroke: 'currentColor' }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-4xl font-bold text-text-primary">{Math.round(campaign.overall_score || 0)}</span>
            <span className="text-xs text-text-muted">/100</span>
          </div>
        </div>
        <span className={`text-xl font-bold ${RATING_COLORS[campaign.overall_rating] || ''}`}>
          {campaign.overall_rating}
        </span>
      </div>

      {/* Verdict Distribution */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Passed', count: campaign.pass_count, color: 'text-severity-clean', bg: 'bg-severity-clean' },
          { label: 'Failed', count: campaign.fail_count, color: 'text-severity-high', bg: 'bg-severity-high' },
          { label: 'Partial', count: campaign.partial_count, color: 'text-severity-medium', bg: 'bg-severity-medium' },
          { label: 'Unclear', count: campaign.unclear_count, color: 'text-text-muted', bg: 'bg-text-muted' },
        ].map(s => (
          <div key={s.label} className="glass rounded-lg p-4 text-center">
            <p className={`text-3xl font-bold ${s.color}`}>{s.count}</p>
            <p className="text-xs text-text-muted mt-1">{s.label}</p>
            <div className="w-full h-1.5 bg-bg-card rounded-full mt-2 overflow-hidden">
              <div className={`h-full ${s.bg} rounded-full transition-all`}
                style={{ width: `${campaign.total_payloads > 0 ? (s.count / campaign.total_payloads) * 100 : 0}%` }} />
            </div>
          </div>
        ))}
      </div>

      {/* Per-Level Breakdown */}
      {campaign.level_scores && Object.keys(campaign.level_scores).length > 0 && (
        <div className="glass rounded-xl p-5 mb-6">
          <h2 className="font-semibold text-text-primary mb-4">Per-Level Breakdown</h2>
          <div className="space-y-3">
            {Object.entries(campaign.level_scores).map(([level, stats]) => (
              <div key={level} className="flex items-center gap-4 bg-bg-card rounded-lg p-3">
                <div className="w-20">
                  <p className="text-sm font-semibold text-text-primary">Level {level}</p>
                  <p className="text-xs text-text-muted">{LEVEL_NAMES[level]}</p>
                </div>
                <div className="flex-1">
                  <div className="w-full h-2 bg-bg-primary rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${
                      stats.score >= 90 ? 'bg-severity-clean' : stats.score >= 70 ? 'bg-severity-low' : stats.score >= 40 ? 'bg-severity-medium' : 'bg-severity-high'
                    }`} style={{ width: `${stats.score}%` }} />
                  </div>
                </div>
                <div className="text-right w-24">
                  <span className={`text-lg font-bold ${
                    stats.score >= 90 ? 'text-severity-clean' : stats.score >= 70 ? 'text-severity-low' : stats.score >= 40 ? 'text-severity-medium' : 'text-severity-high'
                  }`}>{stats.score}</span>
                  <span className="text-xs text-text-muted ml-1">{stats.rating}</span>
                </div>
                <div className="text-xs text-text-muted w-28 text-right">
                  {stats.pass}✅ {stats.fail}❌ {stats.partial}⚠️
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex items-center gap-2 mb-4">
        {[null, 'PASS', 'FAIL', 'PARTIAL', 'UNCLEAR'].map(v => (
          <button key={v || 'all'} onClick={() => setFilter(v)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filter === v
                ? 'bg-accent-purple/15 text-accent-purple'
                : 'bg-bg-card text-text-muted hover:text-text-secondary border border-border'
            }`}>
            {v || 'All'} {v ? `(${campaign.test_results.filter(r => r.verdict === v).length})` : `(${campaign.test_results.length})`}
          </button>
        ))}
      </div>

      {/* Test Results */}
      <div className="space-y-2 mb-8">
        {filteredResults.map((tr) => {
          const isExpanded = expandedId === tr.id
          return (
            <div key={tr.id} className="glass rounded-lg overflow-hidden">
              <button onClick={() => setExpandedId(isExpanded ? null : tr.id)}
                className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-bg-card-hover transition-colors">
                <span className={`text-xs px-2 py-1 rounded-md font-semibold ${VERDICT_STYLES[tr.verdict]}`}>
                  {tr.verdict}
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-bg-card text-text-muted">L{tr.level}</span>
                <span className="text-sm text-text-primary truncate flex-1">{tr.payload_name}</span>
                <span className="text-xs text-text-muted">{tr.category}</span>
                <span className="text-xs text-text-muted w-4">{isExpanded ? '▲' : '▼'}</span>
              </button>
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-border/50 animate-fade-in">
                  <div className="mt-3 space-y-3">
                    <div>
                      <p className="text-xs font-semibold text-text-muted uppercase mb-1">Attack Prompt</p>
                      <pre className="text-xs text-text-secondary bg-bg-card rounded-lg p-3 whitespace-pre-wrap max-h-32 overflow-y-auto">
                        {tr.attack_prompt}
                      </pre>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-text-muted uppercase mb-1">LLM Response</p>
                      <pre className="text-xs text-text-secondary bg-bg-card rounded-lg p-3 whitespace-pre-wrap max-h-48 overflow-y-auto">
                        {tr.llm_response}
                      </pre>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-text-muted">
                      <span>Layer: {tr.evaluation_layer}</span>
                      <span>Confidence: {Math.round(tr.confidence * 100)}%</span>
                      {tr.latency_ms && <span>Latency: {tr.latency_ms}ms</span>}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
