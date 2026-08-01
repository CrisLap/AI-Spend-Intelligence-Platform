const API = import.meta.env.VITE_API_URL ?? "/api";

let _token: string | null = localStorage.getItem("token");

export function setToken(t: string | null) {
  _token = t;
  if (t) localStorage.setItem("token", t);
  else localStorage.removeItem("token");
}
export function getToken() { return _token; }

async function request(path: string, opts: RequestInit = {}) {
  const headers: Record<string,string> = { ...(opts.headers as Record<string,string> || {}) };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const auth = {
  login: (email: string, password: string) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, full_name: string, role?: string) =>
    request("/auth/register", { method: "POST", body: JSON.stringify({ email, password, full_name, role: role ?? "buyer" }) }),
  me: () => request("/auth/me"),
};

export const documents = {
  upload: (file: File, doc_type?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    const url = doc_type ? `/documents/upload?doc_type=${doc_type}` : "/documents/upload";
    return request(url, { method: "POST", body: fd });
  },
  list: (skip = 0, limit = 50) => request(`/documents?skip=${skip}&limit=${limit}`),
  get: (id: number) => request(`/documents/${id}`),
  process: (id: number) => request(`/documents/${id}/process`, { method: "POST" }),
  delete: (id: number) => request(`/documents/${id}`, { method: "DELETE" }),
};

export const classification = {
  classify: (descriptions: string[]) =>
    request("/classification", { method: "POST", body: JSON.stringify({ descriptions }) }),
  updateItem: (id: number, data: Record<string,string|null>) =>
    request(`/classification/line-items/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
};

export const search = {
  semantic: (q: string, top_k = 10) => request(`/search?q=${encodeURIComponent(q)}&top_k=${top_k}`),
};

export const chat = {
  send: (message: string, session_id?: number) =>
    request("/chat", { method: "POST", body: JSON.stringify({ message, session_id }) }),
  sessions: () => request("/chat/sessions"),
  messages: (session_id: number) => request(`/chat/sessions/${session_id}/messages`),
  deleteSession: (id: number) => request(`/chat/sessions/${id}`, { method: "DELETE" }),
};

export const analytics = {
  dashboard: () => request("/analytics/dashboard"),
};

export const anomalies = {
  list: (skip = 0, limit = 50) => request(`/anomalies?skip=${skip}&limit=${limit}`),
};

export const duplicates = {
  list: (skip = 0, limit = 50) => request(`/duplicates?skip=${skip}&limit=${limit}`),
};

export const feedback = {
  create: (data: { document_id: number; line_item_id?: number; original_category?: string; corrected_category: string; comment?: string }) =>
    request("/feedback", { method: "POST", body: JSON.stringify(data) }),
};
