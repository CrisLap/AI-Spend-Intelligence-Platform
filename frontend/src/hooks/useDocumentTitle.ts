import { useEffect } from "react";

const APP_NAME = "SpendIntel";

// Called once per page with its translated title - re-runs (and updates
// document.title) automatically on language switch too, since `t()`
// returns a new string when i18next's language changes and that re-renders
// the calling component.
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
    return () => { document.title = APP_NAME; };
  }, [title]);
}
