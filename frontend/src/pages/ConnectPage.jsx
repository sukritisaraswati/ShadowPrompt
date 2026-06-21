import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { testLLMConnection } from '../utils/api'

const PROVIDER_PRESETS = [
  { name: 'OpenAI', url: 'https://api.openai.com/v1', defaultModel: 'gpt-4o-mini' },
  { name: 'Groq', url: 'https://api.groq.com/openai/v1', defaultModel: 'llama-3.1-8b-instant' },
  { name: 'Together', url: 'https://api.together.xyz/v1', defaultModel: 'meta-llama/Llama-3-8b-chat-hf' },
  { name: 'Custom', url: '', defaultModel: '' },
]

export default function ConnectPage() {
  const [provider, setProvider] = useState(0)
  const [baseUrl, setBaseUrl] = useState(PROVIDER_PRESETS[0].url)
  const [model, setModel] = useState(PROVIDER_PRESETS[0].defaultModel)
  const [apiKey, setApiKey] = useState('')
  const [testing, setTesting] = useState(false)
  const [status, setStatus] = useState(null) // { type: 'success'|'error', message, detail }
  const navigate = useNavigate()

  const selectProvider = (idx) => {
    setProvider(idx)
    setBaseUrl(PROVIDER_PRESETS[idx].url)
    setModel(PROVIDER_PRESETS[idx].defaultModel)
    setStatus(null)
  }

  const handleTest = async () => {
    if (!baseUrl.trim() || !model.trim() || !apiKey.trim()) {
      setStatus({ type: 'error', message: 'Please fill in all fields.' })
      return
    }
    setTesting(true)
    setStatus(null)
    try {
      const result = await testLLMConnection(baseUrl, model, apiKey)
      setStatus({
        type: 'success',
        message: 'Connection successful!',
        detail: `Model: ${result.model} • Latency: ${result.latency_ms}ms`,
      })
    } catch (err) {
      setStatus({
        type: 'error',
        message: err.userMessage || 'Connection failed.',
        detail: err.errorCode || '',
      })
    } finally {
      setTesting(false)
    }
  }

  const handleContinue = () => {
    // Store connection info in sessionStorage (NOT the API key — that stays in state)
    sessionStorage.setItem('lab_connection', JSON.stringify({ baseUrl, model, apiKey }))
    navigate('/lab/configure')
  }

  return (
    <div className="animate-fade-in max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-3">
          ⚔️ <span className="gradient-text">Security Lab</span>
        </h1>
        <p className="text-text-secondary">
          Connect to your LLM to begin security testing. Your API key stays in browser memory only.
        </p>
      </div>

      <div className="glass rounded-2xl p-6">
        {/* Provider Presets */}
        <label className="block text-sm font-medium text-text-muted mb-2">Provider</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
          {PROVIDER_PRESETS.map((p, i) => (
            <button key={p.name} onClick={() => selectProvider(i)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                provider === i
                  ? 'bg-accent-purple/15 text-accent-purple border border-accent-purple/30'
                  : 'bg-bg-card text-text-muted border border-border hover:text-text-secondary'
              }`}>
              {p.name}
            </button>
          ))}
        </div>

        {/* Base URL */}
        <label className="block text-sm font-medium text-text-muted mb-1.5">Base URL</label>
        <input
          type="url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.openai.com/v1"
          className="w-full px-4 py-2.5 rounded-lg bg-bg-card border border-border text-text-primary placeholder-text-muted/50 focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30 outline-none transition-all mb-4 text-sm"
        />

        {/* Model */}
        <label className="block text-sm font-medium text-text-muted mb-1.5">Model</label>
        <input
          type="text"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="gpt-4o-mini"
          className="w-full px-4 py-2.5 rounded-lg bg-bg-card border border-border text-text-primary placeholder-text-muted/50 focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30 outline-none transition-all mb-4 text-sm"
        />

        {/* API Key */}
        <label className="block text-sm font-medium text-text-muted mb-1.5">
          API Key
          <span className="ml-2 text-xs text-accent-cyan font-normal">🔒 Memory-only — never stored</span>
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-..."
          className="w-full px-4 py-2.5 rounded-lg bg-bg-card border border-border text-text-primary placeholder-text-muted/50 focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30 outline-none transition-all mb-5 text-sm font-mono"
        />

        {/* Status Message */}
        {status && (
          <div className={`rounded-lg p-3 mb-5 text-sm ${
            status.type === 'success'
              ? 'bg-severity-clean/10 border border-severity-clean/20 text-severity-clean'
              : 'bg-severity-high/10 border border-severity-high/20 text-severity-high'
          }`}>
            <p className="font-medium">{status.message}</p>
            {status.detail && <p className="text-xs mt-0.5 opacity-80">{status.detail}</p>}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleTest}
            disabled={testing || !baseUrl || !model || !apiKey}
            className="flex-1 px-4 py-2.5 bg-bg-card border border-accent-purple/30 text-accent-purple font-semibold rounded-lg hover:bg-accent-purple/10 transition-all disabled:opacity-40 text-sm"
          >
            {testing ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Testing...
              </span>
            ) : '🔌 Test Connection'}
          </button>

          <button
            onClick={handleContinue}
            disabled={status?.type !== 'success'}
            className="flex-1 px-4 py-2.5 bg-gradient-to-r from-accent-purple to-pink-500 text-white font-semibold rounded-lg hover:opacity-90 transition-all disabled:opacity-30 text-sm"
          >
            Continue →
          </button>
        </div>
      </div>

      {/* Info Card */}
      <div className="glass rounded-xl p-4 mt-6 border-l-4 border-accent-purple/50">
        <h3 className="font-semibold text-text-primary text-sm mb-1">What happens next?</h3>
        <p className="text-xs text-text-secondary leading-relaxed">
          After connecting, you'll choose which attack levels to run (1–3). The lab will send
          each payload to your model, evaluate its response, and give you a real-time security score.
          Your API key is used only for the duration of the session.
        </p>
      </div>
    </div>
  )
}
