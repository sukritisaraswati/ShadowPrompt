import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { streamCampaign, cancelCampaign } from '../utils/api'

const VERDICT_STYLES = {
  PASS: 'bg-severity-clean/15 text-severity-clean border-severity-clean/30',
  FAIL: 'bg-severity-high/15 text-severity-high border-severity-high/30',
  PARTIAL: 'bg-severity-medium/15 text-severity-medium border-severity-medium/30',
  UNCLEAR: 'bg-text-muted/15 text-text-muted border-text-muted/30',
}

const VERDICT_ICONS = { PASS: '✅', FAIL: '❌', PARTIAL: '⚠️', UNCLEAR: '❓' }

export default function RunningPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [verdicts, setVerdicts] = useState([])
  const [progress, setProgress] = useState({ completed: 0, total: 0, pass_count: 0, fail_count: 0, partial_count: 0, unclear_count: 0 })
  const [status, setStatus] = useState('connecting') // connecting, running, completed, cancelled, error
  const [finalData, setFinalData] = useState(null)
  const [error, setError] = useState(null)
  const cancelRef = useRef(null)
  const feedRef = useRef(null)

  const connection = JSON.parse(sessionStorage.getItem('lab_connection') || '{}')

  useEffect(() => {
    if (!connection.apiKey) {
      navigate('/lab/connect')
      return
    }

    const cancel = streamCampaign(
      id,
      connection.apiKey,
      // onEvent
      (eventType, data) => {
        if (eventType === 'campaign_start') {
          setStatus('running')
          setProgress(prev => ({ ...prev, total: data.total_payloads }))
        } else if (eventType === 'verdict') {
          setVerdicts(prev => [...prev, data])
          setProgress(data.progress)
        }
      },
      // onError
      (errMsg) => {
        setError(errMsg)
        setStatus('error')
      },
      // onComplete
      (eventType, data) => {
        if (eventType === 'campaign_complete') {
          setStatus('completed')
          setFinalData(data)
        } else if (eventType === 'campaign_cancelled') {
          setStatus('cancelled')
        } else if (eventType === 'campaign_error') {
          setStatus('error')
          setError(data.error)
        }
      }
    )

    cancelRef.current = cancel
    return () => cancel()
  }, [id])

  // Auto-scroll feed
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [verdicts])

  const handleCancel = async () => {
    try {
      await cancelCampaign(id)
    } catch {}
  }

  const pct = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0

  return (
    <div className="animate-fade-in">
      <div className="text-center mb-6">
        <h1 className="text-3xl font-bold mb-2">
          {status === 'running' ? '🚀' : status === 'completed' ? '✅' : status === 'cancelled' ? '🛑' : '⚠️'}
          {' '}<span className="gradient-text">
            {status === 'running' ? 'Campaign Running' : status === 'completed' ? 'Campaign Complete' : status === 'cancelled' ? 'Campaign Cancelled' : status === 'connecting' ? 'Connecting...' : 'Campaign Error'}
          </span>
        </h1>
        <p className="text-text-secondary text-sm">{connection.model}</p>
      </div>

      {/* Progress Bar */}
      <div className="glass rounded-xl p-5 mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-text-primary">{progress.completed} / {progress.total} tests</span>
          <span className="text-sm font-bold text-accent-purple">{pct}%</span>
        </div>
        <div className="w-full h-3 bg-bg-card rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-accent-purple to-pink-500 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Pass', count: progress.pass_count, color: 'text-severity-clean' },
          { label: 'Fail', count: progress.fail_count, color: 'text-severity-high' },
          { label: 'Partial', count: progress.partial_count, color: 'text-severity-medium' },
          { label: 'Unclear', count: progress.unclear_count, color: 'text-text-muted' },
        ].map(s => (
          <div key={s.label} className="glass rounded-lg p-3 text-center">
            <p className={`text-2xl font-bold ${s.color}`}>{s.count}</p>
            <p className="text-xs text-text-muted">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Live Feed */}
      <div className="glass rounded-xl overflow-hidden mb-4">
        <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            {status === 'running' && <span className="w-2 h-2 rounded-full bg-severity-clean animate-pulse" />}
            Live Verdict Feed
          </h3>
          <span className="text-xs text-text-muted">{verdicts.length} results</span>
        </div>
        <div ref={feedRef} className="max-h-96 overflow-y-auto divide-y divide-border/50">
          {verdicts.length === 0 ? (
            <div className="p-8 text-center text-text-muted text-sm">
              {status === 'connecting' ? 'Connecting to campaign stream...' : 'Waiting for first verdict...'}
            </div>
          ) : (
            verdicts.map((v, i) => (
              <div key={i} className="px-4 py-3 flex items-center gap-3 animate-fade-in hover:bg-bg-card-hover transition-colors">
                <span className="text-lg">{VERDICT_ICONS[v.verdict]}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-text-primary truncate">{v.payload_name}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-bg-card text-text-muted flex-shrink-0">L{v.level}</span>
                  </div>
                  <p className="text-xs text-text-muted truncate">{v.response_preview}</p>
                </div>
                <span className={`text-xs px-2 py-1 rounded-md font-semibold border flex-shrink-0 ${VERDICT_STYLES[v.verdict]}`}>
                  {v.verdict}
                </span>
                <span className="text-xs text-text-muted flex-shrink-0 w-14 text-right">{v.latency_ms}ms</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        {status === 'running' && (
          <button onClick={handleCancel}
            className="flex-1 py-2.5 bg-severity-high/10 border border-severity-high/30 text-severity-high font-semibold rounded-xl hover:bg-severity-high/20 transition-all">
            🛑 Cancel Campaign
          </button>
        )}
        {(status === 'completed' || status === 'cancelled') && (
          <button onClick={() => navigate(`/lab/results/${id}`)}
            className="flex-1 py-2.5 bg-gradient-to-r from-accent-purple to-pink-500 text-white font-semibold rounded-xl hover:opacity-90 transition-all">
            📊 View Full Results
          </button>
        )}
        {status === 'error' && (
          <div className="flex-1">
            <div className="rounded-lg p-3 bg-severity-high/10 border border-severity-high/20 text-severity-high text-sm mb-3">
              {error || 'An unexpected error occurred.'}
            </div>
            <button onClick={() => navigate('/lab/connect')}
              className="w-full py-2.5 bg-bg-card border border-border text-text-primary font-semibold rounded-xl hover:bg-bg-card-hover transition-all">
              ← Back to Connect
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
