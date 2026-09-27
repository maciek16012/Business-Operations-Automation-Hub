const event = $input.first().json;
const execution = event.execution ?? {};
const trigger = event.trigger ?? {};
const message = String(execution.error?.message ?? trigger.error?.message ?? '');
const categories = ['BACKEND_TIMEOUT', 'BACKEND_UNAVAILABLE', 'INVALID_PAYLOAD', 'INGESTION_FAILED'];
const category = categories.find(c => message.includes(c)) ?? 'UNEXPECTED_WORKFLOW_ERROR';
return [{json: {
  category, execution_id: execution.id ?? null, execution_url: execution.url ?? null,
  workflow_id: event.workflow?.id ?? null, failed_node: execution.lastNodeExecuted ?? trigger.error?.node?.name ?? null,
  action: category === 'INVALID_PAYLOAD' ? 'Correct metadata; replay the same message identity' : category === 'INGESTION_FAILED' ? 'Inspect the preserved BOAH case' : 'Restore service and retry the saved execution with the same Message-ID',
  automatic_retry: false
}}];
