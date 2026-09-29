import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import StatsPage from "./pages/StatsPage";
import SubmitPage from "./pages/SubmitPage";

export default function App() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="masthead">
        <div className="masthead__inner">
          <div className="masthead__mark">
            CivicPulse <span>· municipal works</span>
          </div>
          <nav className="nav" aria-label="Sections">
            <NavLink to="/report">Report a problem</NavLink>
            <NavLink to="/queue">Operations queue</NavLink>
            <NavLink to="/overview">Overview</NavLink>
          </nav>
        </div>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<Navigate to="/report" replace />} />
          <Route path="/report" element={<SubmitPage />} />
          <Route path="/queue" element={<DashboardPage />} />
          <Route path="/overview" element={<StatsPage />} />
          <Route path="*" element={<Navigate to="/report" replace />} />
        </Routes>
      </main>
    </>
  );
}
