export default function Footer() {
  return (
    <footer className="border-t border-border py-6 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-text-muted">
          <div className="flex items-center gap-2">
            <span className="gradient-text font-semibold">ShadowPrompt</span>
            <span>v1.0.0</span>
          </div>
          <p>For authorized, educational, and defensive security research only.</p>
          <p>&copy; {new Date().getFullYear()} ShadowPrompt</p>
        </div>
      </div>
    </footer>
  )
}
