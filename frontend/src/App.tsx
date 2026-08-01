import { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
import { getToken, setToken, auth } from "./api";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Documents from "./pages/Documents";
import DocumentView from "./pages/DocumentView";
import Classification from "./pages/Classification";
import SemanticSearch from "./pages/SemanticSearch";
import ChatPage from "./pages/ChatPage";
import AnomaliesPage from "./pages/AnomaliesPage";
import DuplicatesPage from "./pages/DuplicatesPage";

export type User = { id: number; email: string; full_name: string; role: string };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (getToken()) {
      auth.me().then(setUser).catch(() => { setToken(null); setUser(null); }).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  if (loading) return <div className="flex h-screen items-center justify-center text-muted">Loading...</div>;

  if (!user) return <Login onLogin={(u) => { setUser(u); navigate("/"); }} />;

  return (
    <Layout user={user} onLogout={() => { setToken(null); setUser(null); navigate("/login"); }}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/documents/:id" element={<DocumentView />} />
        <Route path="/classification" element={<Classification />} />
        <Route path="/search" element={<SemanticSearch />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/anomalies" element={<AnomaliesPage />} />
        <Route path="/duplicates" element={<DuplicatesPage />} />
      </Routes>
    </Layout>
  );
}
