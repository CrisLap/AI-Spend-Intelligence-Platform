import { Component, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

function ErrorFallback({ error }: { error: Error | null }) {
  const { t } = useTranslation("common");
  return (
    <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm font-semibold text-danger">{t("errorBoundary.title")}</p>
      <p className="text-xs text-muted">{t("errorBoundary.description")}</p>
      <button
        onClick={() => window.location.reload()}
        className="rounded bg-teal px-4 py-1.5 text-xs font-semibold text-surface"
      >
        {t("errorBoundary.reload")}
      </button>
      {import.meta.env.DEV && error && (
        <pre className="mt-2 max-w-full overflow-auto rounded bg-panel-2 p-2 text-left text-[10px] text-muted">
          {error.stack || error.message}
        </pre>
      )}
    </div>
  );
}

type Props = { children: ReactNode };
type State = { error: Error | null };

// Class component because componentDidCatch/getDerivedStateFromError have
// no hook equivalent. Wraps only <Routes> in App.tsx, not the whole app -
// so a crash in one page still leaves the sidebar/nav usable to click away
// from it, instead of a full white-screen.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error(error);
  }

  render() {
    if (this.state.error) return <ErrorFallback error={this.state.error} />;
    return this.props.children;
  }
}
