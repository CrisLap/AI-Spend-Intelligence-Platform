import { useEffect, useState } from "react";
import { anomalies } from "../api";

type Anom = { id: number; description: string; unit_price: number; category: string; supplier: string | null; zscore: number; reason: string; };

export default function AnomaliesPage() {
  const [list, setList] = useState<Anom[]>([]);

  useEffect(() => { anomalies.list().then(setList); }, []);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">Detected Anomalies</h1>
      <p className="text-xs text-muted">Spend items that deviate significantly from their category average.</p>
      {list.length === 0 && <p className="text-ok text-sm">No anomalies detected.</p>}
      <div className="flex flex-col gap-2">
        {list.map((a) => (
          <div key={a.id} className="rounded border border-danger/30 bg-danger/5 p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{a.description}</p>
              <span className="text-xs bg-danger/10 text-danger px-2 py-0.5 rounded">z-score: {a.zscore}</span>
            </div>
            <div className="flex gap-3 mt-1 text-xs text-muted">
              <span>Supplier: {a.supplier || "N/A"}</span>
              <span>Price: €{a.unit_price.toFixed(2)}</span>
              <span>Category: {a.category || "N/A"}</span>
            </div>
            <p className="text-xs text-muted mt-1">{a.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
