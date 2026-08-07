import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { documents, feedback } from "../api";

type Item = { id: number; description: string; quantity: number; unit_price: number; total: number; supplier: string | null; category_label: string | null; confidence: number | null; is_anomaly: boolean; anomaly_reason: string | null; };
type Doc = { id: number; original_name: string; status: string; doc_type: string; line_items: Item[]; };

export default function DocumentView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<Doc | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    documents.get(Number(id)).then(setDoc).catch((err: any) => setError(err.message));
  }, [id]);

  if (error) return <p className="text-danger">{error}</p>;
  if (!doc) return <p className="text-muted">Loading...</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate("/documents")} className="text-xs text-muted hover:text-parchment">← Documents</button>
        <h1 className="text-xl font-bold">{doc.original_name}</h1>
        <span className={`text-xs px-2 py-0.5 rounded ${doc.status === "classified" ? "bg-ok/10 text-ok" : "bg-amber/10 text-amber"}`}>{doc.status}</span>
      </div>
      <div className="rounded border border-border bg-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
            <th className="p-3">Description</th><th className="p-3">Qty</th><th className="p-3">Price</th><th className="p-3">Total</th><th className="p-3">Supplier</th><th className="p-3">Category</th><th className="p-3">Confidence</th><th className="p-3">Anomaly</th>
          </tr></thead>
          <tbody>
            {doc.line_items.map((item) => (
              <tr key={item.id} className="border-b border-border/60 hover:bg-panel-2/30">
                <td className="p-3">{item.description}</td>
                <td className="p-3">{item.quantity}</td>
                <td className="p-3">€{item.unit_price.toFixed(2)}</td>
                <td className="p-3">€{item.total.toFixed(2)}</td>
                <td className="p-3 text-muted">{item.supplier || "-"}</td>
                <td className="p-3">
                  <span className="text-xs bg-teal/10 text-teal px-2 py-0.5 rounded">{item.category_label || "N/A"}</span>
                </td>
                <td className="p-3 text-xs text-muted">{item.confidence ? `${(item.confidence * 100).toFixed(0)}%` : "-"}</td>
                <td className="p-3">
                  {item.is_anomaly ? (
                    <span className="text-xs bg-danger/10 text-danger px-2 py-0.5 rounded" title={item.anomaly_reason || ""}>⚠ Anomaly</span>
                  ) : <span className="text-xs text-ok">✓ OK</span>}
                </td>
              </tr>
            ))}
            {doc.line_items.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-muted">No items extracted</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
