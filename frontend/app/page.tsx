"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, api, BusinessField, CaseData, CaseDetail, fields, jsonBody } from "../lib/api";

import ReviewQueue from "./review-queue";
import OCRPanel from "./ocr-panel";

const editableStatuses = ["RECEIVED", "READY", "REVIEW_REQUIRED"];
const label = (value: string) => value.replaceAll("_", " ");

export default function Home() {
  const [cases, setCases] = useState<CaseData[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<CaseDetail | null>(null);
  const [draft, setDraft] = useState<Partial<Record<BusinessField, string>>>({});
  const [files, setFiles] = useState<File[]>([]);
  const [reason, setReason] = useState("");
  const [attachmentReason, setAttachmentReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    const result = await api<{items: CaseData[]; total: number}>(`/cases?offset=${offset}&limit=25`);
    setCases(result.items); setTotal(result.total);
  }, [offset]);
  useEffect(() => {
    let active = true;
    api<{items: CaseData[]; total: number}>(`/cases?offset=${offset}&limit=25`)
      .then(result => { if (active) { setCases(result.items); setTotal(result.total); } })
      .catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [offset]);

  function show(detail: CaseDetail) { setSelected(detail); setDraft({}); }
  async function run(action: () => Promise<void>, message: string) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  async function selectCase(id: string) {
    show(await api<CaseDetail>(`/cases/${id}`)); setFiles([]); setReason("");
  }
  async function review(action: string) {
    if (!selected) return;
    const options = action === "reject" ? jsonBody({reason}) : {};
    show(await api<CaseDetail>(`/review/${selected.id}/${action}`, {method: "POST", ...options}));
  }
  async function exportFile(kind: string) {
    if (!selected) return;
    const response = await fetch(`${API_BASE}/exports/${selected.id}/${kind}`, {method: "POST"});
    if (!response.ok) { const data = await response.json(); throw new Error(data.error?.message ?? "Export failed"); }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url; link.download = `${selected.public_id}.${kind}`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    show(await api<CaseDetail>(`/cases/${selected.id}`));
  }
  const dirty = Object.keys(draft).length > 0;
  const editable = selected && editableStatuses.includes(selected.status);
  const blocking = selected?.validation_issues.some(i => !i.resolved && ["ERROR", "CRITICAL"].includes(i.severity));

  return <main className="shell">
    <header><p className="eyebrow">OPERATIONS / REVIEW DESK</p><h1>Business Operations Automation Hub</h1><p className="muted">Upload → extract → validate → review → approve → export</p></header>
    {error && <p role="alert" className="error">{error}</p>}
    {notice && <p role="status" className="notice">{notice}</p>}
    <section className="panel stack">
      <div className="toolbar"><h2>Cases ({total})</h2><button disabled={busy} onClick={() => run(async () => {show(await api<CaseDetail>("/cases", {method: "POST", ...jsonBody({})})); setFiles([]);}, "Case created. Upload documents or enter business data.")}>Create case</button><button disabled={busy} onClick={() => run(refresh, "List refreshed")}>Refresh</button></div>
      <div className="table-wrap"><table><thead><tr><th>Case</th><th>Customer / company</th><th>Title</th><th>Source</th><th>Status</th><th>Updated</th></tr></thead><tbody>
        {cases.map(c => <tr key={c.id}><td><button className="link" disabled={busy} onClick={() => run(() => selectCase(c.id), "Case loaded")}>{c.public_id}</button></td><td>{c.company_name || c.customer_name || "—"}</td><td>{c.request_title || "—"}</td><td>{c.source}</td><td><span className="badge">{c.status}</span></td><td>{new Date(c.updated_at).toLocaleString()}</td></tr>)}
        {!cases.length && <tr><td colSpan={6}>No cases on this page. Create a case to begin.</td></tr>}
      </tbody></table></div>
      <div className="toolbar"><button disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button><span>{total ? offset + 1 : 0}–{Math.min(offset + 25, total)} of {total}</span><button disabled={busy || offset + 25 >= total} onClick={() => setOffset(offset + 25)}>Next</button></div>
    </section>
    <ReviewQueue onCase={async id=>{await selectCase(id);await refresh();}}/>
    {selected && <>
      {selected.inbound_message && <section className="panel stack"><h2>Email source</h2>
        <p><strong>From:</strong> {selected.inbound_message.sender_name} &lt;{selected.inbound_message.sender_address}&gt;</p>
        <p><strong>To:</strong> {selected.inbound_message.recipients.map(r => r.address).join(", ") || "—"}</p>
        <p><strong>Subject:</strong> {selected.inbound_message.subject || "(no subject)"}</p>
        <p><strong>Received:</strong> {new Date(selected.inbound_message.received_at).toLocaleString()}</p>
        <p><strong>Message-ID:</strong> {selected.inbound_message.external_message_id || "Missing — stable fingerprint used"}</p>
        <p className="muted">Source: email / {selected.inbound_message.source_type} · {selected.inbound_message.identity_method} · {selected.inbound_message.processing_status}</p>
        <pre>{selected.inbound_message.text_body || "No plain-text body"}</pre>
        {selected.inbound_message.html_body && <details><summary>Original HTML (escaped text)</summary><pre>{selected.inbound_message.html_body}</pre></details>}
      </section>}
      <section className="panel stack"><div className="toolbar"><h2>{selected.public_id}</h2><span className="badge">{selected.status}</span></div>
        <p className="muted">Created {new Date(selected.created_at).toLocaleString()}. Raw extraction remains in the source table below.</p>
        <form onSubmit={e => { e.preventDefault(); run(async () => {
          show(await api<CaseDetail>(`/review/${selected.id}`, {method: "PATCH", ...jsonBody(Object.fromEntries(Object.entries(draft).map(([k,v]) => [k, v || null])))}));
        }, "Corrections saved and validation rerun"); }}>
          <fieldset disabled={busy || !editable}><div className="form-grid">{fields.map(field => <label key={field}>{label(field)}
            <input aria-label={label(field)} value={draft[field] ?? selected[field] ?? ""} onChange={e => setDraft({...draft, [field]: e.target.value})} placeholder={field === "requested_deadline" ? "YYYY-MM-DD" : field === "estimated_value" ? "12500.00" : ""}/>
            {selected.normalization_errors[field] && <small className="error">{selected.normalization_errors[field]}</small>}
          </label>)}</div><button type="submit" disabled={!Object.keys(draft).length}>Save corrections & validate</button></fieldset>
        </form>
        {dirty && <p role="status">Unsaved corrections. Save corrections before validation or approval.</p>}
        <div className="toolbar"><button disabled={busy || !editable || dirty} onClick={() => run(() => review("validate"), "Validation completed")}>Rerun validation</button><button disabled={busy || selected.status !== "READY" || blocking || dirty} onClick={() => run(() => review("approve"), "Case approved")}>Approve</button><button disabled={busy || !["APPROVED", "EXPORTED"].includes(selected.status)} onClick={() => run(() => exportFile("json"), "JSON export generated")}>Export JSON</button><button disabled={busy || !["APPROVED", "EXPORTED"].includes(selected.status)} onClick={() => run(() => exportFile("xlsx"), "XLSX export generated")}>Export XLSX</button></div>
        {editable && <div className="toolbar"><label>Rejection reason<input value={reason} onChange={e => setReason(e.target.value)} maxLength={2000}/></label><button disabled={busy || !reason.trim()} onClick={() => run(() => review("reject"), "Case rejected")}>Reject case</button></div>}
      </section>
      <section className="panel stack"><h2>Attachments</h2><p>UTF-8 .txt fixtures; PDF/PNG/JPEG/TIFF with dual OCR enabled, up to 5 MiB each, maximum 10 files per upload. Exact duplicates within a case are ignored and audited.</p>
        {editable && <form onSubmit={e => {e.preventDefault(); run(async () => {const data = new FormData(); files.forEach(file => data.append("files", file)); show(await api<CaseDetail>(`/uploads/${selected.id}`, {method:"POST", body:data})); setFiles([]);}, "Upload processed; inspect status and validation below");}}><input aria-label="Documents" key={`${selected.id}-${selected.attachments.length}`} type="file" accept=".txt,.pdf,.png,.jpg,.jpeg,.tif,.tiff" multiple disabled={busy} onChange={e => setFiles(Array.from(e.target.files ?? []))}/><button disabled={busy || !files.length}>Upload & process</button></form>}
        {selected.attachments.map(a => <div key={a.id}><a href={`${API_BASE}/uploads/${selected.id}/${a.id}`}>{a.original_filename}</a><span>{a.mime_type} · {a.size_bytes} bytes</span><code className="hash">SHA-256: {a.sha256}</code></div>)}
      </section>
      {selected.ocr_documents?.map(d => <OCRPanel key={d.id} document={d} caseId={selected.id} editable={Boolean(editable && !busy && !dirty)} onReviewed={show}/>)}
      <section className="panel stack"><h2>Validation history</h2>{!selected.validation_issues.length && <p>No recorded issues.</p>}{selected.validation_issues.map(i => <p key={i.id} className={i.resolved ? "muted" : i.severity === "WARNING" ? "" : "error"}><strong>{i.resolved ? "RESOLVED" : i.severity} · {i.code}</strong> — {i.field_name}: {i.message}</p>)}</section>
      {selected.inbound_message && selected.validation_issues.some(i => !i.resolved && ["EMAIL_ATTACHMENT_UNSUPPORTED", "EMAIL_EXTRACTION_FAILED"].includes(i.code)) && <section className="panel stack"><h2>Attachment review</h2><p>Inspect the preserved original and correct business data before acknowledging a document that could not be extracted.</p><label>Attachment review reason<input aria-label="Attachment review reason" value={attachmentReason} onChange={e => setAttachmentReason(e.target.value)} maxLength={2000}/></label>{selected.validation_issues.filter(i => !i.resolved && ["EMAIL_ATTACHMENT_UNSUPPORTED", "EMAIL_EXTRACTION_FAILED"].includes(i.code)).map(i => <button key={i.id} disabled={busy || !editable || dirty || !attachmentReason.trim()} onClick={() => run(async () => {show(await api<CaseDetail>(`/inbound/messages/${selected.inbound_message!.id}/attachments/${i.field_name.replace("attachment:", "")}/review`, {method:"POST", ...jsonBody({reason:attachmentReason})})); setAttachmentReason("");}, "Attachment review recorded and validation rerun")}>Acknowledge review: {selected.attachments.find(a => a.id === i.field_name.replace("attachment:", ""))?.original_filename}</button>)}</section>}
      <section className="panel stack"><h2>Extracted source fields</h2><div className="table-wrap"><table><thead><tr><th>Field</th><th>Raw value</th><th>Normalized value</th><th>Source / provider</th></tr></thead><tbody>{selected.extracted_fields.map(f => <tr key={f.id}><td>{label(f.field_name)}</td><td>{f.raw_value ?? "—"}</td><td>{String(f.normalized_value ?? "—")}</td><td>{selected.attachments.find(a => a.id === f.attachment_id)?.original_filename}<br/>{f.extraction_method}</td></tr>)}</tbody></table></div></section>
      <section className="panel stack"><h2>Saved exports</h2>{selected.exports.map(x => <p key={x.id}>{x.storage_key ? <a href={`${API_BASE}/exports/${x.id}`}>Download {x.export_type.toUpperCase()} · {x.id}</a> : "Export failed"}</p>)}</section>
      <section className="panel stack"><h2>Audit trail</h2><ol>{selected.audit_events.map(a => <li key={a.id}><strong>{label(a.event_type)}</strong> · {a.actor_type} · {new Date(a.created_at).toLocaleString()}<pre>{JSON.stringify(a.details, null, 2)}</pre></li>)}</ol></section>
    </>}
  </main>;
}
