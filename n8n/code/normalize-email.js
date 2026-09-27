// Runs once for all IMAP items. Binary bytes are resolved through n8n's storage helper.
const output = [];
const items = $input.all();
function addresses(value) {
  const values = Array.isArray(value) ? value.flatMap(v => v.value ?? [v]) : (value?.value ?? []);
  return values.map(v => ({address: v.address, name: v.name || null}));
}
for (let index = 0; index < items.length; index++) {
  const item = items[index];
  const mail = item.json;
  const senders = addresses(mail.from);
  if (senders.length !== 1) throw new Error('INVALID_PAYLOAD: exactly one parsed sender is required');
  const attachments = [];
  for (const [key, binary] of Object.entries(item.binary ?? {})) {
    const buffer = await this.helpers.getBinaryDataBuffer(index, key);
    attachments.push({filename: binary.fileName || key, mime_type: binary.mimeType || 'application/octet-stream', content_base64: buffer.toString('base64')});
  }
  output.push({json: {
    source_type: 'imap', external_message_id: mail.messageId || null,
    sender: senders[0], recipients: addresses(mail.to), cc: addresses(mail.cc), reply_to: addresses(mail.replyTo),
    subject: mail.subject || '', received_at: mail.receivedAt || new Date().toISOString(),
    sent_at: mail.date ? new Date(mail.date).toISOString() : null,
    text_body: typeof mail.text === 'string' ? mail.text : '',
    html_body: typeof mail.html === 'string' ? mail.html : null, attachments,
  }, pairedItem: {item: index}});
}
return output;
