/**
 * Typed shapes for the admin JSON API (map-service-admin).
 * JSON blobs whose shape is opaque are typed as `JsonValue`.
 */

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/* ----------------------------- auth ---------------------------------- */

export interface AuthUser {
  username: string;
  role?: 'owner' | 'operator' | 'viewer';
}

/* ------------------------------ ops ---------------------------------- */

export interface HealthItem {
  service: string;
  kind: string;
  ok: boolean;
  latency_ms: number | null;
  http_status?: number | null;
  error?: string | null;
  configured?: boolean | null;
}

export interface HealthResponse {
  services: HealthItem[];
}

export interface PollingBucket {
  last_base_at?: string | null;
  last_tm_fc?: string | null;
  rows: number;
}

export interface PollingData {
  grids: { active_grids: number; total_grids: number };
  short_term: { last_base_at: string | null; rows: number };
  mid_land: { last_tm_fc: string | null; rows: number };
  mid_temp: { last_tm_fc: string | null; rows: number };
}

export interface ForecastTableRow {
  table: string;
  rows: number;
  min_expires_at: string | null;
  max_expires_at: string | null;
}

export interface ForecastRowsData {
  tables: ForecastTableRow[];
}

export interface PlaceSourceRow {
  source: string;
  rows: number;
}

export interface PlacesStats {
  total: number;
  by_source: PlaceSourceRow[];
}

export interface GeminiQuota {
  date_kst: string;
  daily_used: number;
  daily_cap: number;
  daily_remaining: number;
  rpm_bucket: number | string | null;
}

export interface GeminiData {
  connection: { ok: boolean; [key: string]: JsonValue };
  quota: GeminiQuota;
}

export interface StreamRef {
  stream: string;
  length: number;
}

export interface StreamsData {
  done: StreamRef;
  status: StreamRef;
  dlq: StreamRef;
  group: string;
  pending: { pending: number; min: string | null; max: string | null };
}

export interface OverviewData {
  health: HealthItem[];
  polling: PollingData | null;
  places: PlacesStats | null;
  gemini_quota: GeminiQuota | null;
  streams: StreamsData | null;
  errors: Record<string, string>;
}

export interface ExternalProvider {
  provider: string;
  label: string;
  configured: boolean;
  key_masked?: string | null;
  cache_keys?: number | null;
  quota?: JsonValue;
}

export interface ExternalData {
  providers: ExternalProvider[];
}

export interface ProbeResult {
  provider: string;
  ok: boolean;
  latency_ms: number | null;
  detail: JsonValue;
  audit_id: number | string | null;
}

export interface MonitoringPanel {
  title: string;
  url: string;
  embed: boolean;
  height: number;
  description: string;
}

export interface MonitoringData {
  panels: MonitoringPanel[];
}

/* ------------------------------ db ----------------------------------- */

export interface DbTableInfo {
  table: string;
  rows: number;
}

export interface DbTablesResponse {
  schema: string;
  tables: DbTableInfo[];
}

export interface DbColumn {
  name: string;
  data_type: string;
  udt_name: string;
  is_nullable: string;
}

export interface DbIndex {
  indexname: string;
  indexdef: string;
}

export interface DbSchemaResponse {
  table: string;
  columns: DbColumn[];
  indexes: DbIndex[];
}

export interface DbRowsResponse {
  table: string;
  columns: string[];
  rows: Record<string, JsonValue>[];
  total: number;
  limit: number;
  offset: number;
  sort: string | null;
  q: string | null;
  filters: Record<string, string>;
}

/* ----------------------------- users --------------------------------- */

export interface UserListItem {
  id: number | string;
  emailMasked: string;
  nickname: string;
  authProvider: string;
  emailVerified: boolean;
  createdAt: string;
}

export interface UserDetail {
  id: number | string;
  email: string;
  nickname: string;
  profileImageUrl: string | null;
  authProvider: string;
  emailVerified: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PageResponse<T> {
  items: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

/* ------------------------------ jobs --------------------------------- */

export interface JobsStats {
  byStatus: {
    in_progress?: number;
    done?: number;
    failed?: number;
    [key: string]: number | undefined;
  };
  total: number;
  failedLast24h: number;
}

export interface JobItem {
  jobId: string;
  scheduleId: string | number | null;
  status: string;
  error: string | null;
  createdAt: string;
  finishedAt: string | null;
}

export interface DlqItem {
  recordId: string;
  jobId: string | null;
  status: string | null;
  deliveryCount: number;
  error: string | null;
  payloadPreview: string | null;
}

/* ---------------------------- actions -------------------------------- */

export interface KmaRunResult {
  ok: boolean;
  triggered: JsonValue;
}

export interface GridPatchResult {
  ok: boolean;
  changed: boolean;
  before: JsonValue;
  after: JsonValue;
}

export interface ForbiddenZone {
  zone_id: number | string;
  name: string;
  reason: string | null;
  geometry: JsonValue;
  created_at: string;
}

export interface ZoneDeleteResult {
  ok: boolean;
  deleted: JsonValue;
}

export interface DlqActionResult {
  requested: number;
  succeeded: number;
  failed: number;
  failedIds: string[];
}

/* ------------------------------ audit -------------------------------- */

export interface AuditRow {
  id: number | string;
  actor: string;
  action: string;
  target_service: string | null;
  target_schema: string | null;
  target_table: string | null;
  target_id: string | null;
  params_json: JsonValue;
  before_json: JsonValue;
  after_json: JsonValue;
  status: string;
  request_ip: string | null;
  created_at: string;
}

export interface AuditResponse {
  items: AuditRow[];
  total: number;
  limit: number;
  offset: number;
}
