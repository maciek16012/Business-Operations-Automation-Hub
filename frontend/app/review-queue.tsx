"use client";

import { useCallback, useEffect, useState } from "react";
import { api, jsonBody } from "../lib/api";

type Task = {id:string;case_id:string;task_type:string;priority:string;status:string;
  title:string;description:string;created_at:string;payload:{public_case_id:string;attachment:string};
  security_scans?:Record<string,unknown>[]};
type Queue = {items:Task[];total:number;open_count:number};

export default function ReviewQueue({onCase}:{onCase:(id:string)=>Promise<void>}) {
  const [queue,setQueue] = useState<Queue>({items:[],total:0,open_count:0});
  const [task,setTask] = useState<Task|null>(null);
  const [reason,setReason] = useState("");
  const [offset,setOffset] = useState(0);
  const [status,setStatus] = useState("");
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const refresh = useCallback(async () => {
    setQueue(await api<Queue>(`/review-tasks?offset=${offset}&limit=50${status ? `&status=${status}` : ""}`));
  },[status,offset]);
  useEffect(() => {
    let active = true;
    const load = () => api<Queue>(`/review-tasks?offset=${offset}&limit=50${status ? `&status=${status}` : ""}`)
      .then(q=>{if(active)setQueue(q);}).catch(e=>{if(active)setError(e.message);});
    void load(); const timer = setInterval(load,10000);
    return ()=>{active=false;clearInterval(timer);};
  },[status,offset]);
  async function run(action:()=>Promise<void>) {
    setBusy(true);setError("");
    try {await action();} catch(e) {setError(e instanceof Error ? e.message : "Request failed");}
    finally {setBusy(false);}
  }
  async function decide(action:string) {
    if(!task)return;
    setTask(await api<Task>(`/review-tasks/${task.id}/decision`,
      {method:"POST",...jsonBody({action,reason})}));
    await refresh(); await onCase(task.case_id);
  }
  const active = task && ["OPEN","ACKNOWLEDGED"].includes(task.status);
  return <section className="panel stack" aria-label="Review Queue">
    <div className="toolbar"><h2>Review Queue · OPEN {queue.open_count}</h2>
      <label>Status <select value={status} onChange={e=>{setStatus(e.target.value);setOffset(0);}}>
        <option value="">Active</option>{["OPEN","ACKNOWLEDGED","RESOLVED","DISMISSED"].map(s=><option key={s}>{s}</option>)}
      </select></label><button disabled={busy} onClick={()=>run(refresh)}>Refresh queue</button></div>
    {error && <p role="alert" className="error">{error}</p>}
    <p className="muted">Showing {queue.items.length} of {queue.total} tasks. Refreshes every 10 seconds.</p>
    <div className="table-wrap"><table><thead><tr><th>Priority / type</th><th>Case / attachment</th><th>Reason</th><th>Created</th><th>Status</th></tr></thead><tbody>
      {queue.items.map(t=><tr key={t.id}><td><strong>{t.priority}</strong><br/>{t.task_type}</td>
        <td><button className="link" disabled={busy} onClick={()=>run(async()=>{setTask(await api<Task>(`/review-tasks/${t.id}`));setReason("");await onCase(t.case_id);})}>{t.payload.public_case_id}</button><br/>{t.payload.attachment}</td>
        <td>{t.description}</td><td>{new Date(t.created_at).toLocaleString()}</td><td>{t.status}</td></tr>)}
      {!queue.items.length && <tr><td colSpan={5}>No matching review tasks.</td></tr>}
    </tbody></table></div>
    <div className="toolbar"><button disabled={busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous tasks</button><span>{offset+1}–{offset+queue.items.length} / {queue.total}</span><button disabled={busy||offset+50>=queue.total} onClick={()=>setOffset(offset+50)}>Next tasks</button></div>
    {task && <div className="stack"><h3>{task.title} · {task.status}</h3><p>{task.description}</p>
      {task.security_scans?.length ? <details><summary>Security scan history</summary><pre>{JSON.stringify(task.security_scans,null,2)}</pre></details> : null}
      {task.task_type === "SECURITY_QUARANTINE" && <p>Attachment remains quarantined. Closing this incident requires rejecting the entire case. No manual SAFE override is available.</p>}
      {task.task_type === "OCR_REVIEW" && <p>Use the OCR evidence and field review panel below to resolve this task.</p>}
      {active && <><label>Decision reason<input value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label>
      <div className="toolbar">
        {task.status === "OPEN" && <button disabled={busy||!reason.trim()} onClick={()=>run(()=>decide("acknowledge"))}>Acknowledge</button>}
        {["EXTRACTION_FAILURE","UNSUPPORTED_ATTACHMENT"].includes(task.task_type) && <>
          <button disabled={busy||!reason.trim()} onClick={()=>run(()=>decide("resolve"))}>Resolve after manual review</button>
          <button disabled={busy||!reason.trim()} onClick={()=>run(()=>decide("dismiss"))}>Dismiss with reason</button></>}
        <button disabled={busy||!reason.trim()} onClick={()=>run(()=>decide("reject_case"))}>Reject case and close tasks</button>
      </div></>}
    </div>}
  </section>;
}
