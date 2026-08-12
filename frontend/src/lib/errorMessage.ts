import type { TFunction } from "i18next";

// api.ts throws plain Error objects tagged with a stable .code for the
// handful of client-side failure modes it can identify (SSE connection
// issues) - those get a real translation. Everything else is a backend
// HTTPException detail (always English, see backend/app/core/deps.py's
// get_ui_language - translating every route's error strings was scoped
// out) and falls back to err.message as-is, or a generic translated
// message if there's nothing usable at all.
const KNOWN_CODES = new Set(["streamFailed", "streamingNotSupported"]);

export function getErrorMessage(err: unknown, t: TFunction): string {
  const code = (err as { code?: string })?.code;
  if (code && KNOWN_CODES.has(code)) {
    return t(`errors:${code}`, { status: (err as { status?: number })?.status });
  }
  const message = err instanceof Error ? err.message : String(err);
  return message || t("errors:generic");
}
