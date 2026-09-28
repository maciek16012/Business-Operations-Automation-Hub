// Keep only operational identifiers; no document bytes, body, or customer data.
const data = $input.first().json.body;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
if (!data || !uuid.test(data.event_id) || !uuid.test(data.task_id)) {
  throw new Error('INVALID_NOTIFICATION_ID');
}
return [{json:{event_id:data.event_id,task_id:data.task_id}}];
