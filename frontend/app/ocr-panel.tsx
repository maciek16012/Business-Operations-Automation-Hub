"use client";
import { useState } from "react";
import { api, jsonBody, CaseDetail, OCRDocument } from "../lib/api";
export default function OCRPanel({document,caseId,editable,onReviewed}:{document:OCRDocument;caseId:string;editable:boolean;onReviewed:(c:CaseDetail)=>void}) {
 const [values,setValues]=useState<Record<string,string>>({});
 const [reason,setReason]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
 const report=document.report;
 return <section className="panel stack"><h2>Dual OCR / Document intelligence</h2><p><strong>{report.outcome}</strong> · {document.reviewed ? "Human review recorded" : "Original machine decision"}</p>
 <p>Agreement is not proof of correctness. Compare both readings with the original attachment.</p>
 <div className="table-wrap"><table><thead><tr><th>Field</th><th>OCR A / normalized</th><th>OCR B / normalized</th><th>Comparison and reason</th><th>Final value</th></tr></thead><tbody>{report.fields.map(f=><tr key={f.field}><td>{f.field}</td><td>{f.raw_a ?? "—"}<br/>{f.normalized_a ?? "—"}</td><td>{f.raw_b ?? "—"}<br/>{f.normalized_b ?? "—"}</td><td>{f.comparison} · {f.outcome}<br/>{f.reason}</td><td><input aria-label={`OCR ${f.field}`} disabled={!editable || busy} value={values[f.field] ?? document.reviewed_values?.[f.field] ?? f.selected ?? ""} onChange={e=>setValues({...values,[f.field]:e.target.value})}/></td></tr>)}</tbody></table></div>
 <details><summary>Business validation</summary><pre>{JSON.stringify(report.business_validation,null,2)}</pre></details>
 {report.providers.map(p=><details key={p.provider}><summary>{p.provider} {p.provider_version} · {p.processing_time_ms} ms · {p.error ?? "OK"}</summary><pre>{p.raw_text}</pre><details><summary>Raw provider evidence (coordinates and confidence)</summary><pre>{JSON.stringify(p,null,2)}</pre></details></details>)}
 {document.review_reason && <p>Review reason: {document.review_reason}</p>}
 {editable && <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError("");try{const finalValues=Object.fromEntries(report.fields.map(f=>[f.field,values[f.field] ?? document.reviewed_values?.[f.field] ?? f.selected ?? ""]));onReviewed(await api<CaseDetail>(`/ocr/${caseId}/${document.id}/review`,{method:"POST",...jsonBody({reason,values:finalValues})}));setReason("");}catch(e){setError(e instanceof Error?e.message:"Review failed");}finally{setBusy(false);}}}><label>OCR review reason<input aria-label="OCR review reason" value={reason} onChange={e=>setReason(e.target.value)} maxLength={2000}/></label><button disabled={busy || !reason.trim()}>Confirm OCR values & validate</button></form>}
 {error && <p role="alert" className="error">{error}</p>}
 </section>;
}
