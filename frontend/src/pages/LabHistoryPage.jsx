import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listCampaigns } from '../utils/api'

const STATUS_COLORS = {
  running: 'text-accent-blue bg-accent-blue/15',
  completed: 'text-severity-clean bg-severity-clean/15',
  error: 'text-severity-high bg-severity-high/15',
  cancelled: 'text-text-muted bg-bg-card'
}

export default function LabHistoryPage() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)

  useEffect(() => { loadCampaigns() }, [page])

  const loadCampaigns = async () => {
    setLoading(true)
    try {
      const data = await listCampaigns(page, 20)
      setCampaigns(data)
    } catch {
      setCampaigns([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-fade-in max-w-5xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">📋 <span className="gradient-text">Campaign History</span></h1>
          <p className="text-text-secondary text-sm">Review your past LLM security tests.</p>
        </div>
        <Link to="/lab/connect" className="btn-primary py-2 text-sm">New Campaign</Link>
      </div>

      <div className="glass rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-4 border-accent-purple/30 border-t-accent-purple rounded-full animate-spin" />
          </div>
        ) : campaigns.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-text-muted">No campaigns found.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-bg-card text-xs uppercase text-text-muted font-semibold border-b border-border">
                <th className="p-4">Date</th>
                <th className="p-4">Model</th>
                <th className="p-4">Levels</th>
                <th className="p-4">Score</th>
                <th className="p-4">Status</th>
                <th className="p-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {campaigns.map(c => (
                <tr key={c.id} className="hover:bg-bg-card/50 transition-colors">
                  <td className="p-4 text-sm text-text-secondary whitespace-nowrap">
                    {new Date(c.created_at).toLocaleString()}
                  </td>
                  <td className="p-4 text-sm font-medium text-text-primary">
                    {c.model_name}
                  </td>
                  <td className="p-4">
                    <div className="flex gap-1">
                      {c.selected_levels.map(l => (
                        <span key={l} className="text-[10px] px-1.5 py-0.5 bg-bg-primary rounded text-text-muted border border-border">
                          L{l}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="p-4">
                    {c.status === 'completed' ? (
                      <span className={`font-bold ${
                        c.overall_score >= 90 ? 'text-severity-clean' : c.overall_score >= 70 ? 'text-severity-low' : c.overall_score >= 40 ? 'text-severity-medium' : 'text-severity-high'
                      }`}>
                        {Math.round(c.overall_score)}/100
                      </span>
                    ) : (
                      <span className="text-text-muted text-sm">-</span>
                    )}
                  </td>
                  <td className="p-4">
                    <span className={`text-xs px-2 py-1 rounded-md font-medium uppercase ${STATUS_COLORS[c.status] || STATUS_COLORS.error}`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    <Link to={`/lab/results/${c.id}`} className="text-accent-purple hover:underline text-sm font-medium">
                      View Results →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      
      {/* Basic Pagination */}
      <div className="flex justify-center gap-4 mt-6">
        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-4 py-2 bg-bg-card rounded-lg text-sm disabled:opacity-50 hover:bg-bg-card-hover transition-colors">
          Previous
        </button>
        <button onClick={() => setPage(p => p + 1)} disabled={campaigns.length < 20} className="px-4 py-2 bg-bg-card rounded-lg text-sm disabled:opacity-50 hover:bg-bg-card-hover transition-colors">
          Next
        </button>
      </div>
    </div>
  )
}
