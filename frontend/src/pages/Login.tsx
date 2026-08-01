import { useState } from "react";
import { auth, setToken } from "../api";
import type { User } from "../App";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (isRegister) {
        const res = await auth.register(email, password, name);
        setToken(res.access_token);
        onLogin(res.user);
      } else {
        const res = await auth.login(email, password);
        setToken(res.access_token);
        onLogin(res.user);
      }
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-surface">
      <form onSubmit={handle} className="w-full max-w-sm rounded border border-border bg-panel p-6 flex flex-col gap-4">
        <h1 className="text-lg font-bold text-teal">AI Spend Intelligence</h1>
        <p className="text-xs text-muted">{isRegister ? "Create an account" : "Sign in to the platform"}</p>
        {isRegister && (
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" required
            className="rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
        )}
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required
          className="rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required
          className="rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
        {error && <p className="text-xs text-danger">{error}</p>}
        <button type="submit" className="rounded bg-teal py-2 text-sm font-semibold text-surface hover:opacity-90">
          {isRegister ? "Register" : "Sign In"}
        </button>
        <button type="button" onClick={() => setIsRegister(!isRegister)} className="text-xs text-muted hover:text-parchment">
          {isRegister ? "Already have an account? Sign In" : "New user? Register"}
        </button>
      </form>
    </div>
  );
}
