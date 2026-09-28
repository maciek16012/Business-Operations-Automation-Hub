const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const code = fs.readFileSync(path.join(root,'code/review-notification.js'),'utf8');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const run = body => new AsyncFunction('$input', code)({first:()=>({json:{body}})});
test('review payload excludes document/customer data and preserves idempotency identity', async()=>{
  const event_id='11111111-1111-4111-8111-111111111111';
  const task_id='22222222-2222-4222-8222-222222222222';
  assert.deepEqual(await run({event_id,task_id,document:'private',password:'secret'}),[{json:{event_id,task_id}}]);
  assert.deepEqual(await run({event_id,task_id}),await run({event_id,task_id}));
});
test('invalid review identities are rejected',async()=>{
  for(const input of [undefined,{}, {event_id:'bad',task_id:'bad'}])
    await assert.rejects(run(input),/INVALID_NOTIFICATION_ID/);
});
test('workflow is deterministic, credential-free and acknowledges only durable sink response',()=>{
  const flow=JSON.parse(fs.readFileSync(path.join(root,'workflows/review-notifications.json')));
  assert.equal(flow.nodes.find(n=>n.type.endsWith('.code')).parameters.jsCode.replaceAll('\r\n','\n'),code.replaceAll('\r\n','\n'));
  const sink=flow.nodes.find(n=>n.type.endsWith('.httpRequest'));
  assert.equal(sink.parameters.url,'http://backend:8000/api/v1/review-tasks/notifications/receipt');
  assert.equal(sink.maxTries,3);
  assert.equal(sink.onError,undefined);
  assert.ok(flow.nodes.every(n=>!n.credentials));
  assert.equal(flow.nodes[0].parameters.responseMode,'lastNode');
});
