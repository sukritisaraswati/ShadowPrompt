export default function AboutPage() {
  return (
    <div className="animate-fade-in max-w-4xl mx-auto">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold mb-3">
          ℹ️ <span className="gradient-text">About ShadowScan</span>
        </h1>
        <p className="text-text-secondary max-w-2xl mx-auto">
          Understanding how ShadowScan detects prompt injection threats in web content.
        </p>
      </div>

      {/* How It Works */}
      <Section title="🔬 How It Works">
        <p className="text-text-secondary mb-4">
          ShadowScan performs static HTML analysis — it parses the page source code without executing any JavaScript,
          extracts content from 13 different source locations, scans for suspicious patterns across 7 detection categories,
          and calculates a deterministic risk score.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          {['Parse HTML', 'Extract Content', 'Detect Patterns', 'Score Risk'].map((step, i) => (
            <div key={i} className="flex-1 bg-bg-card rounded-lg p-4 text-center">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center text-bg-primary font-bold text-sm mx-auto mb-2">
                {i + 1}
              </div>
              <p className="text-sm font-medium text-text-primary">{step}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Extraction Sources */}
      <Section title="📍 Extraction Sources (13)">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {[
            { source: 'HTML Comments', desc: 'Invisible to users, visible to AI' },
            { source: 'Meta Tags', desc: 'Page metadata often read by AI' },
            { source: 'Image Alt Text', desc: 'Accessibility text processed by AI' },
            { source: 'ARIA Labels', desc: 'Accessibility attributes with context' },
            { source: 'Title Attributes', desc: 'Tooltip text read by AI systems' },
            { source: 'Data Attributes', desc: 'Custom developer fields in HTML' },
            { source: 'Hidden Elements', desc: 'CSS-invisible content in source' },
            { source: 'Visible Text', desc: 'Overt injection in page content' },
            { source: 'Script Contents', desc: 'String literals in JS code' },
            { source: 'Inline Styles', desc: 'Off-screen positioned elements' },
            { source: 'Link/Button Text', desc: 'Clickable element content' },
            { source: 'Noscript Blocks', desc: 'Content for non-JS browsers' },
          ].map(({ source, desc }, i) => (
            <div key={i} className="flex items-center gap-3 bg-bg-card rounded-lg p-3">
              <span className="text-accent-cyan text-sm">▸</span>
              <div>
                <p className="text-sm font-medium text-text-primary">{source}</p>
                <p className="text-xs text-text-muted">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Detection Categories */}
      <Section title="🎯 Detection Categories (7)">
        <div className="space-y-3">
          {[
            { cat: 'Instruction Override', desc: 'Attempts to cancel normal AI behavior', color: 'text-severity-high' },
            { cat: 'Data Exfiltration', desc: 'Attempts to make AI reveal private data', color: 'text-severity-critical' },
            { cat: 'Unauthorized Action', desc: 'Attempts to make AI take real-world actions', color: 'text-severity-high' },
            { cat: 'Persona/Role Override', desc: 'Attempts to give AI a new identity without filters', color: 'text-severity-medium' },
            { cat: 'Stealth Instruction', desc: "Attempts to hide AI's actions from the user", color: 'text-severity-medium' },
            { cat: 'Context Injection', desc: 'Attempts to inject fake system messages', color: 'text-severity-high' },
            { cat: 'Chained Payload Setup', desc: 'Sets up delayed or multi-step attacks', color: 'text-severity-low' },
          ].map(({ cat, desc, color }, i) => (
            <div key={i} className="flex items-start gap-3 bg-bg-card rounded-lg p-4">
              <span className={`font-bold text-lg mt-0.5 ${color}`}>●</span>
              <div>
                <p className="font-semibold text-text-primary">{cat}</p>
                <p className="text-sm text-text-secondary">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Scoring */}
      <Section title="📊 Risk Scoring">
        <p className="text-text-secondary mb-4">
          The risk score is calculated from a combination of source location weight and detection category severity multiplier.
          Multiple unique injection sources earn a bonus. The final score is always capped at 100.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {[
            { range: '0-20', label: 'Clean', color: 'severity-clean' },
            { range: '21-40', label: 'Low', color: 'severity-low' },
            { range: '41-60', label: 'Medium', color: 'severity-medium' },
            { range: '61-80', label: 'High', color: 'severity-high' },
            { range: '81-100', label: 'Critical', color: 'severity-critical' },
          ].map(({ range, label, color }) => (
            <div key={label} className={`rounded-lg p-3 text-center bg-${color}/10`}>
              <p className={`text-lg font-bold text-${color}`}>{range}</p>
              <p className={`text-xs font-semibold text-${color}`}>{label}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Limitations */}
      <Section title="⚠️ Limitations">
        <ul className="space-y-2">
          {[
            'Rule-based detection cannot catch every paraphrase or non-English injection.',
            'Static HTML analysis does not process JavaScript-generated content.',
            'Legitimate security documentation may trigger false positives.',
            'A clean scan does not guarantee the page is safe against all injection techniques.',
            'The scanner detects configured patterns only — novel attack vectors may not be covered.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
              <span className="text-severity-low mt-0.5">•</span>
              {item}
            </li>
          ))}
        </ul>
      </Section>

      {/* Disclaimer */}
      <div className="glass rounded-xl p-5 border-l-4 border-severity-low mb-8">
        <h3 className="font-semibold text-severity-low mb-2">⚖️ Disclaimer</h3>
        <p className="text-sm text-text-secondary leading-relaxed">
          ShadowPrompt is intended for authorized, educational, and defensive security testing only.
          Detection results are heuristic and may include false positives. A low or zero score does not
          certify that the content is safe for AI processing. Users are responsible for ensuring they
          have permission to scan submitted targets.
        </p>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="glass rounded-xl p-6 mb-6">
      <h2 className="text-xl font-bold mb-4 text-text-primary">{title}</h2>
      {children}
    </div>
  )
}
