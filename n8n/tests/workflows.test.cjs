const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
function run(file, items, helpers={}) {
  const fn = new AsyncFunction('$input', fs.readFileSync(path.join(root,'code',file),'utf8'));
  return fn.call({helpers}, {all:()=>items, first:()=>items[0]});
}

test('resolved IMAP metadata and stored binary bytes map without arbitrary headers', async () => {
  const bytes = Buffer.from('NIP: 5260250274\nEstimated value: 12 500,00 PLN');
  const source = {json:{messageId:'<one@example.test>',from:{value:[{address:'a@example.com',name:'Example'}]},to:{value:[{address:'b@example.com'}]},cc:{value:[{address:'c@example.com'}]},replyTo:{value:[{address:'reply@example.com'}]},subject:'Zażółć',date:'2026-09-27T12:00:00+02:00',text:'Plain body',html:'<script>bad()</script>',headers:{authorization:'do not forward'}},binary:{attachment_0:{fileName:'../document.txt',mimeType:'text/plain',data:'filesystem-v2'}}};
  const result = await run('normalize-email.js',[source],{getBinaryDataBuffer:async(index,key)=>{assert.equal(index,0);assert.equal(key,'attachment_0');return bytes;}});
  assert.equal(result.length,1);
  assert.equal(result[0].json.sent_at,'2026-09-27T10:00:00.000Z');
  assert.equal(result[0].json.external_message_id,'<one@example.test>');
  assert.equal(result[0].json.subject,'Zażółć');
  assert.equal(result[0].json.reply_to[0].address,'reply@example.com');
  assert.equal(result[0].json.html_body,'<script>bad()</script>');
  assert.equal(result[0].json.headers,undefined);
  assert.deepEqual(Buffer.from(result[0].json.attachments[0].content_base64,'base64'),bytes);
});

test('a multi-email trigger batch produces one item per message including no attachments', async () => {
  const mail = address => ({json:{from:{value:[{address}]},text:'body'},binary:{}});
  const results = await run('normalize-email.js',[mail('a@example.com'),mail('b@example.com')]);
  assert.equal(results.length,2);
  assert.deepEqual(results.map(r=>r.json.sender.address),['a@example.com','b@example.com']);
  assert.deepEqual(results[0].json.attachments,[]);
});

test('created, duplicate and review responses are successful, failed case is actionable', async () => {
  for (const [result,status,outcome] of [['created','READY','accepted'],['duplicate','EXPORTED','idempotent_noop'],['created','REVIEW_REQUIRED','operator_review']]) {
    const actual = await run('classify-response.js',[{json:{body:{result,status,case_id:'case',message_id:'message',processing_status:'processed'}}}]);
    assert.equal(actual[0].json.delivery_outcome,outcome);
  }
  await assert.rejects(run('classify-response.js',[{json:{result:'created',status:'FAILED',case_id:'case',message_id:'message',processing_status:'failed'}}]),/INGESTION_FAILED/);
});

test('transport and payload errors are classified without leaking raw error text', async () => {
  for (const [error,category] of [[{message:'connect ECONNREFUSED 10.0.0.1'},'BACKEND_UNAVAILABLE'],[{message:'ETIMEDOUT secret-token'},'BACKEND_TIMEOUT'],[{message:'Bad payload',httpCode:422},'INVALID_PAYLOAD'],[{message:'Oops'},'UNEXPECTED_WORKFLOW_ERROR']]) {
    await assert.rejects(run('classify-response.js',[{json:{error}}]), e=>e.message.startsWith(category) && !e.message.includes('secret-token'));
  }
  await assert.rejects(run('classify-response.js',[{json:{unexpected:true}}]),/UNEXPECTED_WORKFLOW_ERROR/);
});

test('error trigger emits bounded recovery context and no body or secrets', async () => {
  const result = await run('error-summary.js',[{json:{execution:{id:'123',error:{message:'BACKEND_TIMEOUT secret'},lastNodeExecuted:'Classify delivery'},workflow:{id:'workflow'},password:'secret'}}]);
  assert.equal(result[0].json.category,'BACKEND_TIMEOUT');
  assert.equal(result[0].json.automatic_retry,false);
  assert.equal(JSON.stringify(result).includes('secret'),false);
});

test('sanitized workflows embed the reviewed code and cannot access DB or BOAH storage', () => {
  for (const filename of ['inbound-email.json','inbound-email-fixture.json','inbound-email-error.json']) {
    const workflow=JSON.parse(fs.readFileSync(path.join(root,'workflows',filename)));
    for (const node of workflow.nodes) {
      assert.equal(node.credentials,undefined);
      assert.ok(!/postgres|readWriteFile|executeCommand/i.test(node.type));
      const mapping={'Normalize email':'normalize-email.js','Fixture binary':'fixture-to-binary.js','Classify delivery':'classify-response.js','Recovery context':'error-summary.js'};
      if(mapping[node.name]) assert.equal(node.parameters.jsCode,fs.readFileSync(path.join(root,'code',mapping[node.name]),'utf8').replaceAll('\r\n','\n'));
    }
    if(filename!=='inbound-email-error.json') {
      const request=workflow.nodes.find(n=>n.name==='Send to BOAH');
      assert.equal(request.maxTries,3);
      assert.equal(request.parameters.url,'http://backend:8000/api/v1/inbound/email');
      assert.equal(workflow.settings.errorWorkflow,'boahEmailErrors2');
    }
  }
});
