/**
 * Route table -- blueprint section 8.
 *
 * Lab and ShadowScan are separate navigation groups sharing one shell.
 */

import { Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import About from "@/pages/About";
import Home from "@/pages/Home";
import NotFound from "@/pages/NotFound";
import Compare from "@/pages/lab/Compare";
import Configure from "@/pages/lab/Configure";
import Connect from "@/pages/lab/Connect";
import History from "@/pages/lab/History";
import Results from "@/pages/lab/Results";
import Running from "@/pages/lab/Running";
import DemoLab from "@/pages/scan/DemoLab";
import ScanHistory from "@/pages/scan/ScanHistory";
import ScanResults from "@/pages/scan/ScanResults";
import Scanner from "@/pages/scan/Scanner";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />

        {/* ShadowPrompt Lab */}
        <Route path="lab">
          <Route path="connect" element={<Connect />} />
          <Route path="configure" element={<Configure />} />
          <Route path="running" element={<Running />} />
          <Route path="results/:id" element={<Results />} />
          <Route path="history" element={<History />} />
          <Route path="compare" element={<Compare />} />
        </Route>

        {/* ShadowScan */}
        <Route path="scan">
          <Route index element={<Scanner />} />
          <Route path="results/:id" element={<ScanResults />} />
          <Route path="demo" element={<DemoLab />} />
          <Route path="history" element={<ScanHistory />} />
        </Route>

        <Route path="about" element={<About />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
