return $input.all().map(item => {
  const response = item.json;
  const body = response.body ?? response;
  if (response.error) {
    const error = response.error;
    const message = String(error.message ?? error);
    const status = Number(error.httpCode ?? error.statusCode ?? error.status ?? 0);
    let category = 'UNEXPECTED_WORKFLOW_ERROR';
    if (/timed?\s*out|ETIMEDOUT|ESOCKETTIMEDOUT|ECONNABORTED|timeout/i.test(message)) category = 'BACKEND_TIMEOUT';
    else if (/ECONNREFUSED|ENOTFOUND|EAI_AGAIN|service refused|connection.*(refused|closed)|not.*reachable/i.test(message)) category = 'BACKEND_UNAVAILABLE';
    else if ((status >= 400 && status < 500) || /\b(400|413|415|422)\b|invalid.*payload|could not be processed/i.test(message)) category = 'INVALID_PAYLOAD';
    else if (status >= 500) category = 'BACKEND_UNAVAILABLE';
    throw new Error(category + ': bounded delivery attempts exhausted; inspect execution and replay after fixing the cause');
  }
  if (!['created', 'duplicate'].includes(body.result) || !body.case_id || !body.message_id) {
    throw new Error('UNEXPECTED_WORKFLOW_ERROR: unrecognized backend response');
  }
  if (body.processing_status === 'failed' || body.status === 'FAILED') {
    throw new Error('INGESTION_FAILED: backend preserved a failed case ' + body.case_id + '; inspect it, do not create another message identity');
  }
  return {json: {...body, delivery_outcome: body.result === 'duplicate' ? 'idempotent_noop' : body.status === 'REVIEW_REQUIRED' ? 'operator_review' : 'accepted'}};
});
