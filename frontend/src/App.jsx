import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/layout/Navbar'
import Footer from './components/layout/Footer'
import ScannerPage from './pages/ScannerPage'
import ResultsPage from './pages/ResultsPage'
import DemoLabPage from './pages/DemoLabPage'
import HistoryPage from './pages/HistoryPage'
import AboutPage from './pages/AboutPage'

export default function App() {
  return (
    <>
      <Navbar />
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<Navigate to="/scan" replace />} />
          <Route path="/scan" element={<ScannerPage />} />
          <Route path="/scan/results/:id" element={<ResultsPage />} />
          <Route path="/scan/demo" element={<DemoLabPage />} />
          <Route path="/scan/history" element={<HistoryPage />} />
          <Route path="/about" element={<AboutPage />} />
        </Routes>
      </main>
      <Footer />
    </>
  )
}
