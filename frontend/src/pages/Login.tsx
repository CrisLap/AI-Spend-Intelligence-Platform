import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { auth, setToken } from "../api";
import type { User } from "../App";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import Card from "../components/Card";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const { t } = useTranslation(["login", "common"]);
  useDocumentTitle(t("common:tagline"));
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();
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
      <form onSubmit={handle} className="w-full max-w-sm">
        <Card padding="lg" className="flex flex-col gap-4">
          <h1 className="text-lg font-bold text-teal">{t("common:tagline")}</h1>
          <p className="text-xs text-muted">{isRegister ? t("createAccount") : t("signInPrompt")}</p>
          {isRegister && (
            <>
              <label htmlFor={nameId} className="sr-only">{t("fullNamePlaceholder")}</label>
              <input id={nameId} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("fullNamePlaceholder")} required
                className="rounded-full border border-border bg-panel-2 px-4 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" />
            </>
          )}
          <label htmlFor={emailId} className="sr-only">{t("emailPlaceholder")}</label>
          <input id={emailId} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("emailPlaceholder")} required
            className="rounded-full border border-border bg-panel-2 px-4 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" />
          <label htmlFor={passwordId} className="sr-only">{t("passwordPlaceholder")}</label>
          <input
            id={passwordId} type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder={t("passwordPlaceholder")} required
            // Only enforced when registering: accounts created before the
            // 10-character rule was added may still have shorter passwords
            // already hashed in the DB, and this must not block their login.
            minLength={isRegister ? 10 : undefined}
            className="rounded-full border border-border bg-panel-2 px-4 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" />
          {isRegister && <p className="text-xs text-muted -mt-2">{t("passwordHint")}</p>}
          {error && <p className="text-xs text-danger">{error}</p>}
          <button type="submit" className="rounded-full bg-teal py-2 text-sm font-semibold text-surface hover:opacity-90">
            {isRegister ? t("register") : t("signIn")}
          </button>
          <button type="button" onClick={() => setIsRegister(!isRegister)} className="text-xs text-muted hover:text-parchment">
            {isRegister ? t("switchToSignIn") : t("switchToRegister")}
          </button>
        </Card>
      </form>
    </div>
  );
}
