export type Recommendation = {
  title: string;
  reason: string;
  supplier?: string | null;
  category?: string | null;
  estimated_saving?: number | null;
  currency: string;
  confidence: string;
  evidence: string[];
};

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "text-ok",
  medium: "text-amber",
  low: "text-muted",
};

const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", USD: "$", GBP: "£" };

export default function RecommendationCard({ rec }: { rec: Recommendation }) {
  return (
    <div className="flex flex-col gap-2 rounded border border-border bg-panel p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-parchment">{rec.title}</h3>
        <span className={`shrink-0 text-xs uppercase tracking-wide ${CONFIDENCE_STYLE[rec.confidence] ?? "text-muted"}`}>
          {rec.confidence}
        </span>
      </div>

      {rec.estimated_saving != null && (
        <p className="text-2xl font-bold text-teal">
          {CURRENCY_SYMBOL[rec.currency] ?? `${rec.currency} `}
          {rec.estimated_saving.toLocaleString()}
          <span className="ml-1 text-xs font-normal text-muted">/ anno stimato</span>
        </p>
      )}

      <p className="text-sm text-muted">{rec.reason}</p>

      {(rec.supplier || rec.category) && (
        <p className="text-xs text-muted">
          {rec.supplier && <span>Fornitore: {rec.supplier}</span>}
          {rec.supplier && rec.category && " · "}
          {rec.category && <span>Categoria: {rec.category}</span>}
        </p>
      )}

      {rec.evidence.length > 0 && (
        <div className="mt-1 flex flex-col gap-1 rounded bg-panel-2 p-2 text-xs text-muted">
          {rec.evidence.map((e, i) => (
            <p key={i}>{e}</p>
          ))}
        </div>
      )}
    </div>
  );
}
