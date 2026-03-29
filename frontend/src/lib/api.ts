const API_BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...options })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || 'Request failed')
  }
  return response.json()
}

export interface Document {
  id: string; filename: string; input_format: string; output_format: string;
  mode: 'balanced' | 'compliant'; status: 'processing' | 'ready' | 'failed' | 'nuked' | 'expired';
  entity_count: number; pii_report: { entity_type: string; count: number }[];
  download_count: number; max_downloads: number; created_at: string; expires_at: string; nuked_at: string | null;
}
export interface Mapping { pseudonym: string; original_value: string; entity_type: string }
export interface DocumentDetail extends Document { mappings: Mapping[] }
export interface TokenInfo { url: string; expires_at: string; ttl_seconds: number }
export interface TokenStatus { has_active_token: boolean; url?: string; expires_at?: string; ttl_seconds?: number }

export const api = {
  uploadDocument(file: File, mode: string) {
    const fd = new FormData(); fd.append('file', file); fd.append('mode', mode)
    return request<{ id: string; status: string }>('/documents', { method: 'POST', body: fd })
  },
  listDocuments: () => request<Document[]>('/documents'),
  getDocument: (id: string) => request<DocumentDetail>(`/documents/${id}`),
  createToken: (id: string) => request<TokenInfo>(`/documents/${id}/token`, { method: 'POST' }),
  revokeToken: (id: string) => request<{ status: string }>(`/documents/${id}/token`, { method: 'DELETE' }),
  getTokenStatus: (id: string) => request<TokenStatus>(`/documents/${id}/token/status`),
  getMappingCsvUrl: (id: string) => `${API_BASE}/documents/${id}/mapping.csv`,
}
