// Local fixture adapter reproduces the IMAP resolved item and n8n binary storage.
// The webhook is local-only; it has no configurable destination URL or credentials.
const input = $input.first().json.body;
if (!input || !input.mail) throw new Error('INVALID_PAYLOAD: expected mail and attachments');
const binary = {};
for (const [i, attachment] of (input.attachments || []).entries()) {
  binary['attachment_' + i] = await this.helpers.prepareBinaryData(
    Buffer.from(attachment.content_base64, 'base64'), attachment.filename, attachment.mime_type
  );
}
return [{json: input.mail, binary}];
