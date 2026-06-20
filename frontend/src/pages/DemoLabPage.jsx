import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDemoPages, scanDemoPage } from '../utils/api'

const DIFFICULTY_COLORS = {
  Basic: 'text-severity-clean bg-severity-clean/10',
  Intermediate: 'text-severity-low bg-severity-low/10',
  Advanced: 'text-severity-high bg-severity-high/10',
}

export default function DemoLabPage() {
  const [demos, setDemos] = useState([])
  const [loading, setLoading] = useState(true)
  const [scanningId, setScanningId] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    loadDemos()
  }, [])

  const loadDemos = async () => {
    try {
      const data = await getDemoPages()
      setDemos(data)
    } catch {
      // Fallback if backend is not running
      setDemos([])
    } finally {
      setLoading(false)
    }
  }

  const handleScan = async (pageId) => {
    setScanningId(pageId)
    try {
      const result = await scanDemoPage(pageId)
      navigate(`/scan/results/${result.id}`)
    } catch (err) {
      alert(err.userMessage || 'Failed to scan demo page')
    } finally {
      setScanningId(null)
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold mb-3">
          🧪 <span className="gradient-text">Demo Lab</span>
        </h1>
        <p className="text-text-secondary max-w-2xl mx-auto">
          Explore pre-built injection demo pages to understand how different prompt injection techniques work.
          Each page demonstrates a specific hiding location and attack category.
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-10 h-10 border-4 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin" />
        </div>
      ) : demos.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl">
          <p className="text-text-muted text-lg">No demo pages available. Please ensure the backend is running.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {demos.map((demo, i) => (
            <div key={demo.id}
              className="glass rounded-xl p-5 hover:border-accent-cyan/30 transition-all duration-300 animate-slide-up group"
              style={{ animationDelay: `${i * 80}ms` }}>
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-semibold text-text-primary group-hover:text-accent-cyan transition-colors">
                  {demo.name}
                </h3>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${DIFFICULTY_COLORS[demo.difficulty] || ''}`}>
                  {demo.difficulty}
                </span>
              </div>
              <p className="text-sm text-text-secondary mb-3 leading-relaxed">{demo.description}</p>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs px-2 py-0.5 rounded-md bg-accent-blue/10 text-accent-blue font-medium">
                    {demo.technique}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-md bg-accent-purple/10 text-accent-purple font-medium">
                    {demo.expected_category}
                  </span>
                </div>
                <button
                  id={`demo-scan-${demo.id}`}
                  onClick={() => handleScan(demo.id)}
                  disabled={scanningId === demo.id}
                  className="px-3 py-1.5 bg-gradient-to-r from-accent-cyan to-accent-blue text-bg-primary text-xs font-semibold rounded-lg hover:opacity-90 transition-all disabled:opacity-40"
                >
                  {scanningId === demo.id ? (
                    <span className="flex items-center gap-1">
                      <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Scanning
                    </span>
                  ) : '▶ Scan'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Educational Note */}
      <div className="mt-8 glass rounded-xl p-5 border-l-4 border-severity-low">
        <h3 className="font-semibold text-severity-low mb-1">⚠️ Educational Purpose Only</h3>
        <p className="text-sm text-text-secondary">
          These demo pages contain simulated prompt injection payloads designed for learning and testing purposes.
          All payloads are fictional and harmless. They demonstrate how an attacker might hide instructions in HTML.
        </p>
      </div>
    </div>
  )
}
