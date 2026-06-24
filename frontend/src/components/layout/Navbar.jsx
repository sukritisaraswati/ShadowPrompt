import { NavLink, useLocation } from 'react-router-dom'

const scanItems = [
  { to: '/scan', label: 'Scanner', icon: '🔍', end: true },
  { to: '/scan/demo', label: 'Demo Lab', icon: '🧪' },
  { to: '/scan/history', label: 'History', icon: '📋' },
]

const labItems = [
  { to: '/lab/connect', label: 'Connect', icon: '🔌' },
  { to: '/lab/configure', label: 'Configure', icon: '⚙️' },
  { to: '/lab/history', label: 'History', icon: '📋' },
  { to: '/lab/compare', label: 'Compare', icon: '⚖️' },
]

export default function Navbar() {
  const location = useLocation()
  const isLabSection = location.pathname.startsWith('/lab')

  return (
    <nav className="glass sticky top-0 z-50 border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center text-bg-primary font-bold text-lg transition-transform group-hover:scale-110">
              S
            </div>
            <div>
              <span className="text-lg font-bold gradient-text">ShadowPrompt</span>
            </div>
          </NavLink>

          {/* Nav Links */}
          <div className="flex items-center gap-1">
            {/* Service Toggle */}
            <div className="hidden sm:flex items-center gap-0.5 bg-bg-card rounded-lg p-0.5 mr-2">
              <NavLink to="/scan"
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  !isLabSection ? 'bg-accent-cyan/15 text-accent-cyan' : 'text-text-muted hover:text-text-secondary'
                }`}>
                Scan
              </NavLink>
              <NavLink to="/lab/connect"
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  isLabSection ? 'bg-accent-purple/15 text-accent-purple' : 'text-text-muted hover:text-text-secondary'
                }`}>
                Lab
              </NavLink>
            </div>

            {/* Context-dependent nav items */}
            {(isLabSection ? labItems : scanItems).map(({ to, label, icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${
                    isActive
                      ? isLabSection ? 'bg-accent-purple/10 text-accent-purple' : 'bg-accent-cyan/10 text-accent-cyan'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-card'
                  }`
                }
              >
                <span className="text-base">{icon}</span>
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}

            <NavLink to="/about"
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${
                  isActive ? 'bg-accent-cyan/10 text-accent-cyan' : 'text-text-secondary hover:text-text-primary hover:bg-bg-card'
                }`
              }>
              <span className="text-base">ℹ️</span>
              <span className="hidden sm:inline">About</span>
            </NavLink>
          </div>
        </div>
      </div>
    </nav>
  )
}
