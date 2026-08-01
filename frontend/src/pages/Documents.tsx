import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { documents } from "../api";

type Doc = { id: number; original_name: string; doc_type: string; status: string; created_at: string; };

export default function Documents() {
  const [list, setList] = useState<Doc[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  function load() { documents.list().then(setList); }
  useEffect(load, []);

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const doc = await documents.upload(file);
      await documents.process(doc.id);
      load();
    } catch (err: any) { alert(err.message); }
    finally { setUploading(false); fileRef.current!.value = ""; }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Documents</h1>
        <div className="flex gap-2 items-center">
          <input ref={fileRef} type="file" accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg" className="text-xs text-muted file:mr-2 file:rounded file:border-file:border-border file:bg-panel-2 file:text-xs file:text-parchment" />
          <button onClick={handleUpload} disabled={uploading} className="rounded bg-teal px-4 py-1.5 text-xs font-semibold text-surface disabled:opacity-50">
            {uploading ? "Uploading..." : "Upload & Analyze"}
          </button>
        </div>
      </div>
      <div className="rounded border border-border bg-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
            <th className="p-3">Name</th><th className="p-3">Type</th><th className="p-3">Status</th><th className="p-3">Date</th><th className="p-3"></th>
          </tr></thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.id} className="border-b border-border/60 hover:bg-panel-2/50 cursor-pointer" onClick={() => navigate(`/documents/${d.id}`)}>
                <td className="p-3">{d.original_name}</td>
                <td className="p-3 text-muted">{d.doc_type}</td>
                <td className="p-3"><span className={`text-xs px-2 py-0.5 rounded ${d.status === "classified" ? "bg-ok/10 text-ok" : d.status === "failed" ? "bg-danger/10 text-danger" : "bg-amber/10 text-amber"}`}>{d.status}</span></td>
                <td className="p-3 text-muted text-xs">{new Date(d.created_at).toLocaleDateString()}</td>
                <td className="p-3 text-right">
                  <button onClick={(e) => { e.stopPropagation(); documents.delete(d.id).then(load); }} className="text-xs text-danger hover:underline">Delete</button>
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted text-sm">No documents uploaded</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
