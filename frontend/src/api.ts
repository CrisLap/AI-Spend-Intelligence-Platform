const API = import.meta.env.VITE_API_URL ?? "/api";

let _token: string | null = localStorage.getItem("token");

export function setToken(t: string | null) {
  _token = t;
  if (t) localStorage.setItem("token", t);
  else localStorage.removeItem("token");
}
export function getToken() { return _token; }

// Any page that gets a 401 (expired/invalid token) needs the whole app to
// react - clear the token and send the user back to the login screen -
// not just fail silently where the request happened to be made.
let _onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  _onUnauthorized = fn;
}

export type SSEEvent = { event: string; data: any };

// Parses a text/event-stream response into {event, data} objects as they
// arrive. Deliberately not EventSource: EventSource can't send the
// Authorization header this app's auth relies on everywhere else, so this
// reads the stream via fetch()+ReadableStream instead, which does support
// custom headers - see backend/app/api/cost_saving.py's endpoint docstring
// for the same tradeoff on the server side.
async function* streamSSE(path: string): AsyncGenerator<SSEEvent> {
  const headers: Record<string, string> = {};
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) {
    if (res.status === 401 && _onUnauthorized) _onUnauthorized();
    throw new Error(`Stream request failed (${res.status})`);
  }
  if (!res.body) throw new Error("Streaming is not supported by this browser/response");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const eventMatch = raw.match(/^event: (.+)$/m);
      const dataMatch = raw.match(/^data: ([\s\S]+)$/m);
      if (dataMatch) {
        yield { event: eventMatch?.[1] ?? "message", data: JSON.parse(dataMatch[1]) };
      }
    }
  }
}

async function request(path: string, opts: RequestInit = {}) {
  const headers: Record<string,string> = { ...(opts.headers as Record<string,string> || {}) };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (!res.ok) {
    if (res.status === 401 && _onUnauthorized) _onUnauthorized();
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const auth = {
  login: (email: string, password: string) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, full_name: string) =>
    request("/auth/register", { method: "POST", body: JSON.stringify({ email, password, full_name }) }),
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
  retrain: () => request("/classification/retrain", { method: "POST" }),
};

export const users = {
  list: () => request("/users"),
  updateRole: (id: number, role: string) =>
    request(`/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
  auditLog: (id: number, limit = 100) => request(`/users/${id}/audit-log?limit=${limit}`),
  delete: (id: number) => request(`/users/${id}`, { method: "DELETE" }),
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

export const costSaving = {
  analyze: (goal: string, agent_type = "cost_saving") =>
    request("/cost-saving/analyze", { method: "POST", body: JSON.stringify({ goal, agent_type }) }),
  analyzeStream: (goal: string, agent_type = "cost_saving") =>
    streamSSE(`/cost-saving/analyze/stream?goal=${encodeURIComponent(goal)}&agent_type=${agent_type}`),
  history: (skip = 0, limit = 20, agent_type?: string) =>
    request(`/cost-saving/history?skip=${skip}&limit=${limit}${agent_type ? `&agent_type=${agent_type}` : ""}`),
  historyRun: (id: number) => request(`/cost-saving/history/${id}`),
};

export const assistant = {
  send: (message: string, session_id?: number) =>
    request("/assistant", { method: "POST", body: JSON.stringify({ message, session_id }) }),
};

export const feedback = {
  create: (data: { document_id: number; line_item_id?: number; original_category?: string; corrected_category: string; comment?: string }) =>
    request("/feedback", { method: "POST", body: JSON.stringify(data) }),
};
