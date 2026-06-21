import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPayloads, createCampaign } from '../utils/api'

const LEVEL_ICONS = { 1: '🟢', 2: '🟡', 3: '🔴' }
const LEVEL_COLORS = {
  1: 'border-severity-clean/30 hover:border-severity-clean/60',
  2: 'border-severity-low/30 hover:border-severity-low/60',
  3: 'border-severity-high/30 hover:border-severity-high/60',
}
const LEVEL_ACTIVE = {
  1: 'border-severity-clean bg-severity-clean/10',
  2: 'border-severity-low bg-severity-low/10',
  3: 'border-severity-high bg-severity-high/10',
}

export default function ConfigurePage() {
  const [levels, setLevels] = useState([])
  const [selectedLevels, setSelectedLevels] = useState([1, 2, 3])
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  // Get connection info from sessionStorage
  const connection = JSON.parse(sessionStorage.getItem('lab_connection') || '{}')

  useEffect(() => {
    if (!connection.apiKey) {
      navigate('/lab/connect')
      return
    }
    loadLevels()
  }, [])

  const loadLevels = async () => {
    try {
      const data = await getPayloads()
      setLevels(data.levels || [])
    } catch {
      setLevels([])
    }
  }

  const toggleLevel = (level) => {
    setSelectedLevels(prev =>
      prev.includes(level)
        ? prev.filter(l => l !== level)
        : [...prev, level].sort()
    )
  }

  const totalPayloads = levels
    .filter(l => selectedLevels.includes(l.level))
    .reduce((sum, l) => sum + l.payload_count, 0)

  const handleStart = async () => {
    if (selectedLevels.length === 0) {
      setError('Select at least one level.')
      return
    }
    setStarting(true)
    setError(null)
    try {
      const result = await createCampaign(
        connection.baseUrl,
        connection.model,
        selectedLevels,
        connection.apiKey,
      )
      navigate(`/lab/running/${result.id}`)
    } catch (err) {
      setError(err.userMessage || 'Failed to start campaign.')
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="animate-fade-in max-w-3xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-3">
          ⚙️ <span className="gradient-text">Configure Campaign</span>
        </h1>
        <p className="text-text-secondary">
          Select attack levels to test against <span className="text-accent-purple font-medium">{connection.model}</span>
        </p>
      </div>

      {/* Connection Summary */}
      <div className="glass rounded-xl p-4 mb-6 flex items-center gap-3">
        <div className="w-3 h-3 rounded-full bg-severity-clean animate-pulse" />
        <div className="text-sm">
          <span className="text-text-muted">Connected to </span>
          <span className="text-text-primary font-medium">{connection.model}</span>
          <span className="text-text-muted"> via </span>
          <span className="text-text-secondary font-mono text-xs">{connection.baseUrl}</span>
        </div>
      </div>

      {/* Level Selection */}
      <div className="space-y-4 mb-6">
        {levels.map((level) => {
          const isSelected = selectedLevels.includes(level.level)
          return (
            <button
              key={level.level}
              onClick={() => toggleLevel(level.level)}
              className={`w-full text-left glass rounded-xl p-5 border-2 transition-all duration-300 ${
                isSelected ? LEVEL_ACTIVE[level.level] : LEVEL_COLORS[level.level]
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all ${
                    isSelected
                      ? 'bg-accent-purple border-accent-purple text-white'
                      : 'border-border'
                  }`}>
                    {isSelected && <span className="text-xs">✓</span>}
                  </div>
                  <div>
                    <h3 className="font-semibold text-text-primary">
                      {LEVEL_ICONS[level.level]} Level {level.level} — {level.name}
                    </h3>
                    <span className="text-xs text-text-muted">{level.difficulty} • {level.payload_count} payloads</span>
                  </div>
                </div>
              </div>
              <p className="text-sm text-text-secondary ml-9 mb-3">{level.description}</p>
              <div className="flex flex-wrap gap-1.5 ml-9">
                {level.categories.map(cat => (
                  <span key={cat} className="text-xs px-2 py-0.5 rounded-md bg-bg-card text-text-muted">
                    {cat}
                  </span>
                ))}
              </div>
            </button>
          )
        })}
      </div>

      {/* Summary & Launch */}
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm text-text-muted">Total payloads to run</p>
            <p className="text-3xl font-bold text-accent-purple">{totalPayloads}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-text-muted">Estimated time</p>
            <p className="text-lg font-semibold text-text-primary">~{Math.ceil(totalPayloads * 2 / 60)} min</p>
          </div>
        </div>

        {error && (
          <div className="rounded-lg p-3 mb-4 bg-severity-high/10 border border-severity-high/20 text-severity-high text-sm">
            {error}
          </div>
        )}

        <button
          onClick={handleStart}
          disabled={starting || selectedLevels.length === 0}
          className="w-full py-3 bg-gradient-to-r from-accent-purple to-pink-500 text-white font-bold rounded-xl hover:opacity-90 transition-all disabled:opacity-30 text-lg"
        >
          {starting ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Starting Campaign...
            </span>
          ) : `🚀 Launch Campaign (${totalPayloads} tests)`}
        </button>
      </div>
    </div>
  )
}
