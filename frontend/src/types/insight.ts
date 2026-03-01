export interface Insight {
  id: string;
  user_id: string;
  org_id: string | null;
  conversation_id: string;
  message_id: string | null;
  title: string;
  summary: string;
  content: string;
  categories: string[];
  enrichment_task_count: number;
  is_bookmarked: boolean;
  created_at: string;
  user_email?: string; // admin view only
}
