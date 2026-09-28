"""Real PDF + image through upload and n8n email; no mock OCR."""
import base64,json,uuid
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'datasets/ocr/results/e2e';OUT.mkdir(parents=True,exist_ok=True)
API='http://localhost:8000/api/v1'
run=uuid.uuid4().hex[:8]
with httpx.Client(timeout=180) as c:
    created=c.post(API+'/cases',json={'customer_name':'Synthetic OCR Operator','customer_email':'ocr@example.com','request_title':'Dual OCR PDF acceptance '+run});created.raise_for_status();cid=created.json()['id']
    pdf=ROOT/'datasets/ocr/input/dev/dev-01-digital.pdf'
    response=c.post(API+'/uploads/'+cid,files={'files':(pdf.name,pdf.read_bytes(),'application/pdf')});response.raise_for_status();case=response.json()
    assert len(case['ocr_documents'])==1 and case['status']=='REVIEW_REQUIRED'
    doc=case['ocr_documents'][0]
    assert all(p['raw_text'] and p['pages'] and p['raw_provider_output'] and not p['error'] for p in doc['report']['providers'])
    assert doc['report']['providers'][0]['provider']=='tesseract' and doc['report']['providers'][1]['provider']=='paddle'
    assert c.post(API+f'/review/{cid}/approve').status_code==409
    # Leave upload case for independent UI human-review verification.
    original=case
    image=ROOT/'datasets/ocr/input/dev/dev-07-table.png'
    identity=f'<ocr-e2e-{run}@example.com>'
    fixture={'mail':{'messageId':identity,'from':{'value':[{'address':'ocr@example.com','name':'Synthetic OCR Operator'}]},'to':{'value':[{'address':'office@example.com'}]},'subject':'OCR table '+run,'receivedAt':'2026-09-27T12:00:00Z','date':'2026-09-27T12:00:00Z','text':'Synthetic scanned table.'},'attachments':[{'filename':image.name,'mime_type':'image/png','content_base64':base64.b64encode(image.read_bytes()).decode()}]}
    response=c.post('http://localhost:5678/webhook/boah-email-fixture-m2',json=fixture);response.raise_for_status();mail=response.json();mid=mail['case_id']
    detail=c.get(API+'/cases/'+mid).json();mdoc=detail['ocr_documents'][0]
    assert len(detail['ocr_documents'])==1 and all(not p['error'] for p in mdoc['report']['providers'])
    assert detail['status']=='REVIEW_REQUIRED'
    replay=c.post('http://localhost:5678/webhook/boah-email-fixture-m2',json=fixture);replay.raise_for_status()
    assert replay.json()['result']=='duplicate' and replay.json()['case_id']==mid
    gt=json.loads((ROOT/'datasets/ocr/ground_truth/dev/dev-07-table.json').read_text(encoding='utf-8'))
    reviewed=c.post(API+f"/ocr/{mid}/{mdoc['id']}/review",json={'values':gt['fields'],'reason':'Verified synthetic original scan and both independent OCR readings'});reviewed.raise_for_status()
    assert reviewed.json()['status']=='READY'
    assert reviewed.json()['ocr_documents'][0]['report']==mdoc['report']
    approved=c.post(API+f'/review/{mid}/approve');approved.raise_for_status()
    for kind in ('json','xlsx'):
        export=c.post(API+f'/exports/{mid}/{kind}');export.raise_for_status();(OUT/f'email-export.{kind}').write_bytes(export.content)
    report={'result':'PASS','run_id':run,'upload_case_id':cid,'upload_public_id':case['public_id'],'upload_document_id':doc['id'],'upload_outcome':doc['report']['outcome'],'upload_status':'REVIEW_REQUIRED (left for UI verification)','email_case_id':mid,'email_public_id':detail['public_id'],'email_outcome':mdoc['report']['outcome'],'email_final_status':c.get(API+'/cases/'+mid).json()['status'],'email_replay':'duplicate','email_review':'READY then APPROVED and JSON/XLSX','providers':[{'provider':p['provider'],'version':p['provider_version'],'latency_ms':p['processing_time_ms']} for p in doc['report']['providers']]}
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
