export interface DatasetInfo {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  table_name: string | null;
  organization_id?: string | null;
  created_by: string | null;
}

export interface DocumentInfo {
  id: string;
  name: string;
  description: string | null;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  page_count: number;
  extracted_text_preview: string | null;
  dataset_id: string | null;
  created_by: string;
  created_at: string;
}
