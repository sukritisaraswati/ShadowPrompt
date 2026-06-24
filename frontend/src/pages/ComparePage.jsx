import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listCampaigns, getCampaign } from '../utils/api'

export default function ComparePage() {
  const [campaignsList, setCampaignsList] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [comparisonData, setComparisonData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Load completed campaigns for selection
    listCampaigns(1, 50, 'completed').then(data => {
      setCampaignsList(data)
      setLoading(false)
    })
  }, [])

  const handleSelect = async (id) => {
    if (selectedIds.includes(id)) {
      setSelectedIds(prev => prev.filter(x => x !== id))
      setComparisonData(prev => prev.filter(x => x.id !== id))
    } else {
      if (selectedIds.length >= 3) {
        alert('You can compare up to 3 models at a time.')
        return
      }
      setSelectedIds(prev => [...prev, id])
      const data = await getCampaign(id)
      setComparisonData(prev => [...prev, data])
    }
  }

  if (loading) return (
    <div className="flex justify-center py-20">
      <div className="w-10 h-10 border-4 border-accent-purple/30 border-t-accent-purple rounded-full animate-spin" />
    </div>
  )

  return (
    <div className="animate-fade-in max-w-6xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-2">⚖️ <span className="gradient-text">Model Comparison</span></h1>
        <p className="text-text-secondary text-sm">Select up to 3 completed campaigns to compare their security resilience.</p>
      </div>

      <div className="glass rounded-xl p-6 mb-8">
        <h2 className="text-sm font-semibold text-text-muted uppercase mb-4">Select Campaigns</h2>
        <div className="flex flex-wrap gap-2">
          {campaignsList.length === 0 ? (
            <p className="text-text-muted text-sm">No completed campaigns available to compare. <Link to="/lab/connect" className="text-accent-purple hover:underline">Run a campaign first.</Link></p>
          ) : (
            campaignsList.map(c => (
              <button key={c.id} onClick={() => handleSelect(c.id)}
                className={`px-4 py-2 rounded-lg text-sm transition-all border ${
                  selectedIds.includes(c.id) 
                  ? 'bg-accent-purple/20 border-accent-purple text-text-primary' 
                  : 'bg-bg-card border-border hover:border-text-muted text-text-secondary'
                }`}>
                {c.model_name} <span className="text-xs opacity-50 ml-1">({Math.round(c.overall_score)})</span>
              </button>
            ))
          )}
        </div>
      </div>

      {comparisonData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 animate-fade-in">
          {comparisonData.map(c => (
            <div key={c.id} className="glass rounded-2xl p-6 flex flex-col h-full">
              <div className="text-center mb-6">
                <h3 className="font-bold text-xl mb-1 text-text-primary truncate" title={c.model_name}>{c.model_name}</h3>
                <p className="text-xs text-text-muted mb-4">{new Date(c.created_at).toLocaleDateString()}</p>
                <div className="relative w-32 h-32 mx-auto mb-2">
                  <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
                    <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" strokeWidth="8" className="text-bg-card" />
                    <circle cx="60" cy="60" r="50" fill="none" strokeWidth="8"
                      strokeDasharray={`${(c.overall_score || 0) * 3.14} 314`} strokeLinecap="round"
                      className={c.overall_score >= 90 ? 'text-severity-clean' : c.overall_score >= 70 ? 'text-severity-low' : c.overall_score >= 40 ? 'text-severity-medium' : 'text-severity-high'}
                      style={{ stroke: 'currentColor' }} />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-3xl font-bold">{Math.round(c.overall_score || 0)}</span>
                  </div>
                </div>
                <div className={`font-bold ${c.overall_score >= 90 ? 'text-severity-clean' : c.overall_score >= 70 ? 'text-severity-low' : c.overall_score >= 40 ? 'text-severity-medium' : 'text-severity-high'}`}>
                  {c.overall_rating}
                </div>
              </div>

              <div className="space-y-3 flex-1">
                <div className="flex justify-between text-sm bg-bg-card p-2 rounded">
                  <span className="text-text-muted">Total Payloads</span>
                  <span className="font-medium text-text-primary">{c.total_payloads}</span>
                </div>
                <div className="flex justify-between text-sm bg-severity-clean/10 p-2 rounded">
                  <span className="text-severity-clean font-medium">Passed</span>
                  <span className="text-severity-clean font-bold">{c.pass_count}</span>
                </div>
                <div className="flex justify-between text-sm bg-severity-high/10 p-2 rounded">
                  <span className="text-severity-high font-medium">Failed</span>
                  <span className="text-severity-high font-bold">{c.fail_count}</span>
                </div>
                <div className="flex justify-between text-sm bg-bg-card p-2 rounded">
                  <span className="text-text-muted">Levels Tested</span>
                  <span className="font-medium text-text-primary text-right text-xs">
                    {c.selected_levels.map(l => `L${l}`).join(', ')}
                  </span>
                </div>
              </div>
              
              <div className="mt-6 pt-4 border-t border-border/50 text-center">
                <Link to={`/lab/results/${c.id}`} className="text-accent-purple hover:underline text-sm">Full Report →</Link>
              </div>
            </div>
          ))}
          
          {comparisonData.length < 3 && (
            <div className="border-2 border-dashed border-border rounded-2xl p-6 flex flex-col items-center justify-center text-text-muted min-h-[400px]">
              <span className="text-4xl mb-2">+</span>
              <p className="text-sm">Select another model</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
