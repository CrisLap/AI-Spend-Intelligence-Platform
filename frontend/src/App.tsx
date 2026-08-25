import { lazy, Suspense, useEffect, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getToken, setToken, setUnauthorizedHandler, auth } from "./api";
import Layout from "./components/Layout";
import BackendWakingBanner from "./components/BackendWakingBanner";
import ToastContainer from "./components/ToastContainer";
import ErrorBoundary from "./components/ErrorBoundary";
import Login from "./pages/Login";
import Documents from "./pages/Documents";
import DocumentView from "./pages/DocumentView";
import Classification from "./pages/Classification";
import SemanticSearch from "./pages/SemanticSearch";
import AnomaliesPage from "./pages/AnomaliesPage";
import DuplicatesPage from "./pages/DuplicatesPage";
import AdminUsers from "./pages/AdminUsers";

// Pull in recharts (Dashboard) / react-markdown (Chat, Cost Saving) only
// when the user actually navigates there - these two libraries were the
// bulk of the >500kB main-bundle warning at build time.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const CostSavingAgentPage = lazy(() => import("./pages/CostSavingAgentPage"));

export type User = { id: number; email: string; full_name: string; role: string };

export default function App() {
  const { t } = useTranslation("common");
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // A 401 from ANY request (not just the initial session check) must log
    // the user out and send them back to login - previously only the very
    // first load checked this, so an expired token mid-session left every
    // page silently failing with no way back in short of a manual logout.
    setUnauthorizedHandler(() => {
      setToken(null);
      setUser(null);
      navigate("/login");
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  useEffect(() => {
    if (getToken()) {
      auth.me().then(setUser).catch(() => { setToken(null); setUser(null); }).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  return (
    <>
      <BackendWakingBanner />
      <ToastContainer />
      {loading ? (
        <div className="flex h-screen items-center justify-center text-muted">{t("loading")}</div>
      ) : !user ? (
        <Login onLogin={(u) => { setUser(u); navigate("/"); }} />
      ) : (
        <Layout user={user} onLogout={() => { setToken(null); setUser(null); navigate("/login"); }}>
          <ErrorBoundary key={location.pathname}>
            <Suspense fallback={<div className="flex h-full items-center justify-center text-muted">{t("loading")}</div>}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/documents" element={<Documents />} />
                <Route path="/documents/:id" element={<DocumentView />} />
                <Route path="/classification" element={<Classification />} />
                <Route path="/search" element={<SemanticSearch />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/cost-saving" element={<CostSavingAgentPage />} />
                <Route path="/anomalies" element={<AnomaliesPage />} />
                <Route path="/duplicates" element={<DuplicatesPage />} />
                {user.role === "admin" && <Route path="/admin" element={<AdminUsers />} />}
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </Layout>
      )}
    </>
  );
}
