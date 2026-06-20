import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/scan', label: 'Scanner', icon: '🔍' },
  { to: '/scan/demo', label: 'Demo Lab', icon: '🧪' },
  { to: '/scan/history', label: 'History', icon: '📋' },
  { to: '/about', label: 'About', icon: 'ℹ️' },
]

export default function Navbar() {
  return (
    <nav className="glass sticky top-0 z-50 border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <NavLink to="/scan" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center text-bg-primary font-bold text-lg transition-transform group-hover:scale-110">
              S
            </div>
            <div>
              <span className="text-lg font-bold gradient-text">ShadowPrompt</span>
              <span className="hidden sm:inline text-xs text-text-muted ml-2 font-medium">ShadowScan</span>
            </div>
          </NavLink>

          {/* Nav Links */}
          <div className="flex items-center gap-1">
            {navItems.map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/scan'}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-accent-cyan/10 text-accent-cyan'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-card'
                  }`
                }
              >
                <span className="text-base">{icon}</span>
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      </div>
    </nav>
  )
}
