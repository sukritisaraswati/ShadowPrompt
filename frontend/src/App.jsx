import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/layout/Navbar'
import Footer from './components/layout/Footer'

// ShadowScan pages
import ScannerPage from './pages/ScannerPage'
import ResultsPage from './pages/ResultsPage'
import DemoLabPage from './pages/DemoLabPage'
import HistoryPage from './pages/HistoryPage'
import AboutPage from './pages/AboutPage'

// Lab pages
import HomePage from './pages/HomePage'
import ConnectPage from './pages/ConnectPage'
import ConfigurePage from './pages/ConfigurePage'
import RunningPage from './pages/RunningPage'
import CampaignResultsPage from './pages/CampaignResultsPage'

export default function App() {
  return (
    <>
      <Navbar />
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          {/* Home */}
          <Route path="/" element={<HomePage />} />

          {/* ShadowScan */}
          <Route path="/scan" element={<ScannerPage />} />
          <Route path="/scan/results/:id" element={<ResultsPage />} />
          <Route path="/scan/demo" element={<DemoLabPage />} />
          <Route path="/scan/history" element={<HistoryPage />} />

          {/* ShadowPrompt Lab */}
          <Route path="/lab/connect" element={<ConnectPage />} />
          <Route path="/lab/configure" element={<ConfigurePage />} />
          <Route path="/lab/running/:id" element={<RunningPage />} />
          <Route path="/lab/results/:id" element={<CampaignResultsPage />} />

          {/* About */}
          <Route path="/about" element={<AboutPage />} />
        </Routes>
      </main>
      <Footer />
    </>
  )
}
