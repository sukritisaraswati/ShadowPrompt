import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <div className="animate-fade-in">
      {/* Hero Section */}
      <div className="text-center py-12">
        <div className="text-5xl mb-4">🛡️</div>
        <h1 className="text-4xl md:text-5xl font-bold mb-4">
          <span className="gradient-text">ShadowPrompt</span>
        </h1>
        <p className="text-xl text-text-secondary max-w-2xl mx-auto mb-2">
          LLM Security Testing Lab
        </p>
        <p className="text-text-muted max-w-xl mx-auto">
          Detect, analyze, and defend against prompt injection attacks —
          from hidden webpage threats to direct jailbreak attempts.
        </p>
      </div>

      {/* Service Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto mb-12">
        {/* ShadowScan Card */}
        <Link to="/scan" className="group">
          <div className="glass rounded-2xl p-6 h-full hover:border-accent-cyan/40 transition-all duration-300 hover:-translate-y-1">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center text-xl">
                🔍
              </div>
              <div>
                <h2 className="text-xl font-bold text-text-primary group-hover:text-accent-cyan transition-colors">
                  ShadowScan
                </h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-severity-clean/10 text-severity-clean font-medium">
                  Live
                </span>
              </div>
            </div>
            <p className="text-text-secondary text-sm mb-4 leading-relaxed">
              Scan webpages for hidden prompt injection threats. Paste a URL or upload
              an HTML file to analyze 13 source locations across 7 detection categories.
            </p>
            <div className="flex items-center gap-4 text-xs text-text-muted">
              <span className="flex items-center gap-1">📍 13 Sources</span>
              <span className="flex items-center gap-1">🎯 7 Categories</span>
              <span className="flex items-center gap-1">📊 0-100 Score</span>
            </div>
          </div>
        </Link>

        {/* Lab Card */}
        <Link to="/lab/connect" className="group">
          <div className="glass rounded-2xl p-6 h-full hover:border-accent-purple/40 transition-all duration-300 hover:-translate-y-1">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-purple to-pink-500 flex items-center justify-center text-xl">
                ⚔️
              </div>
              <div>
                <h2 className="text-xl font-bold text-text-primary group-hover:text-accent-purple transition-colors">
                  Security Lab
                </h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-accent-purple/10 text-accent-purple font-medium">
                  Live
                </span>
              </div>
            </div>
            <p className="text-text-secondary text-sm mb-4 leading-relaxed">
              Connect your LLM and run structured attack campaigns. Test resistance to
              85 payloads across 3 difficulty levels with real-time verdicts.
            </p>
            <div className="flex items-center gap-4 text-xs text-text-muted">
              <span className="flex items-center gap-1">⚡ 85 Payloads</span>
              <span className="flex items-center gap-1">🏷️ 3 Levels</span>
              <span className="flex items-center gap-1">📡 Live SSE</span>
            </div>
          </div>
        </Link>
      </div>

      {/* How It Works */}
      <div className="max-w-4xl mx-auto mb-12">
        <h2 className="text-2xl font-bold text-center mb-8 text-text-primary">How It Works</h2>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          {[
            { icon: '🔗', title: 'Connect', desc: 'Link your LLM via API key' },
            { icon: '⚙️', title: 'Configure', desc: 'Choose attack levels' },
            { icon: '🚀', title: 'Run', desc: 'Watch live SSE verdicts' },
            { icon: '📊', title: 'Analyze', desc: 'Review security scores' },
          ].map((step, i) => (
            <div key={i} className="glass rounded-xl p-5 text-center animate-slide-up" style={{ animationDelay: `${i * 100}ms` }}>
              <div className="text-3xl mb-2">{step.icon}</div>
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center text-bg-primary font-bold text-sm mx-auto mb-2">
                {i + 1}
              </div>
              <h3 className="font-semibold text-text-primary text-sm">{step.title}</h3>
              <p className="text-xs text-text-muted mt-1">{step.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Stats Bar */}
      <div className="glass rounded-xl p-6 max-w-4xl mx-auto mb-8">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
          {[
            { value: '85', label: 'Attack Payloads', color: 'text-accent-cyan' },
            { value: '15', label: 'Attack Categories', color: 'text-accent-blue' },
            { value: '2', label: 'Evaluation Layers', color: 'text-accent-purple' },
            { value: '13', label: 'Extraction Sources', color: 'text-severity-clean' },
          ].map((stat, i) => (
            <div key={i}>
              <p className={`text-3xl font-bold ${stat.color}`}>{stat.value}</p>
              <p className="text-xs text-text-muted mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Security Note */}
      <div className="max-w-4xl mx-auto glass rounded-xl p-5 border-l-4 border-accent-cyan mb-8">
        <h3 className="font-semibold text-accent-cyan mb-1">🔒 API Key Security</h3>
        <p className="text-sm text-text-secondary">
          Your API keys are stored <strong>only in browser memory</strong> — never in databases, localStorage, or server logs.
          Keys are passed via request headers and discarded after each call. Refreshing the page clears all credentials.
        </p>
      </div>
    </div>
  )
}
