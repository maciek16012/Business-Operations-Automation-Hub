export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
export const fields = ["customer_name", "customer_email", "company_name", "tax_id", "request_title", "request_description", "requested_deadline", "currency", "estimated_value"] as const;
export type BusinessField = typeof fields[number];
export type CaseData = Record<BusinessField, string | null> & { source: "manual_upload" | "api" | "email"; id: string; public_id: string; status: string; created_at: string; updated_at: string; normalization_errors: Record<string, string> };
export type Attachment = { id: string; original_filename: string; mime_type: string; size_bytes: number; sha256: string };
export type Extracted = { id: string; attachment_id: string; field_name: string; raw_value: string | null; normalized_value: string | null; extraction_method: string };
export type Issue = { id: string; code: string; severity: string; field_name: string; message: string; resolved: boolean };
export type Audit = { id: string; event_type: string; actor_type: string; created_at: string; details: Record<string, unknown> };
export type InboundMessage = { id: string; source_type: string; external_message_id: string | null; sender_address: string; sender_name: string | null; subject: string; received_at: string; text_body: string; html_body: string | null; identity_method: string; processing_status: string; recipients: {address:string;name:string|null}[] };
export type CaseDetail = CaseData & { documents: AdaptiveDocument[]; security_scans: {attachment_id:string;verdict:string;reason:string;scanner_version:string|null}[]; ocr_documents: OCRDocument[]; inbound_message: InboundMessage | null; attachments: Attachment[]; extracted_fields: Extracted[]; validation_issues: Issue[]; audit_events: Audit[]; exports: {id: string; export_type: string; storage_key: string | null}[] };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error?.message ?? (data?.detail ? JSON.stringify(data.detail) : `API error ${response.status}`));
  }
  return response.json() as Promise<T>;
}

export const jsonBody = (value: unknown): RequestInit => ({headers: {"Content-Type": "application/json"}, body: JSON.stringify(value)});

export type OCRDocument = {id:string;attachment_id:string;reviewed:boolean;review_reason:string|null;reviewed_values:Record<string,string>|null;report:{outcome:string;business_validation:Record<string,unknown>;providers:{provider:string;provider_version:string;raw_text:string;processing_time_ms:number;error:string|null}[];fields:{field:string;raw_a:string|null;raw_b:string|null;normalized_a:string|null;normalized_b:string|null;selected:string|null;comparison:string;outcome:string;reason:string}[]}};

export type TableCell = {id:string;row:number;column:number;raw_value:string|null;corrected_value:string|null;confidence:number;source:string;uncertain:boolean;bbox:number[]|null};
export type AdaptiveTable = {id:string;page:number;row_count:number;column_count:number;source:string;irregular:boolean;cells:TableCell[];issues:{code:string;message:string;row?:number;column?:number}[]};
export type AdaptiveDocument = {id:string;attachment_id:string;document_type:string;confidence:number;classifier:string;reasons:string[];strategy:string;review_required:boolean;reviewed:boolean;revision:number;raw_text:string;pages:{page:number}[];tables:AdaptiveTable[]};
