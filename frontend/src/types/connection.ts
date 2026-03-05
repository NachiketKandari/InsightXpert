export interface UserDatabaseConnection {
  id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  is_active: boolean;
  is_verified: boolean;
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateConnectionPayload {
  name: string;
  connection_string: string;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  table_count: number | null;
}
