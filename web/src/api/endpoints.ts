import { apiUrl, buildQuery, del, get, patch, post, put } from './client';
import type { QueryParams } from './client';
import type {
  AuditResponse,
  AuthUser,
  DbRowsResponse,
  DbSchemaResponse,
  DbTablesResponse,
  DlqActionResult,
  DlqItem,
  ExternalData,
  ForbiddenZone,
  ForecastRowsData,
  GeminiData,
  GridPatchResult,
  HealthResponse,
  JobItem,
  JobsStats,
  KmaRunResult,
  MonitoringData,
  OverviewData,
  PageResponse,
  PlacesStats,
  PollingData,
  ProbeResult,
  StreamsData,
  UserDetail,
  UserListItem,
  ZoneDeleteResult,
} from './types';

/* ------------------------------ auth --------------------------------- */

export const authApi = {
  me: () => get<AuthUser>('/v1/auth/me', { silent401: true }),
  login: (username: string, password: string) =>
    post<AuthUser>('/v1/auth/login', { username, password }),
  logout: () => post<void>('/v1/auth/logout'),
};

/* ------------------------------- ops --------------------------------- */

export const opsApi = {
  overview: () => get<OverviewData>('/v1/ops/overview'),
  health: () => get<HealthResponse>('/v1/ops/health'),
  polling: () => get<PollingData>('/v1/ops/polling'),
  forecastRows: () => get<ForecastRowsData>('/v1/ops/forecast-rows'),
  placesStats: () => get<PlacesStats>('/v1/ops/places-stats'),
  gemini: () => get<GeminiData>('/v1/ops/gemini'),
  streams: () => get<StreamsData>('/v1/ops/streams'),
  external: () => get<ExternalData>('/v1/ops/external'),
  probe: (provider: string) =>
    post<ProbeResult>(`/v1/ops/external/${encodeURIComponent(provider)}/probe`),
  monitoring: () => get<MonitoringData>('/v1/ops/monitoring'),
};

/* -------------------------------- db --------------------------------- */

export interface DbRowsParams {
  limit?: number;
  offset?: number;
  sort?: string;
  q?: string;
  filters?: Record<string, string>;
}

function dbRowsQuery(params: DbRowsParams): string {
  const base: QueryParams = {
    limit: params.limit,
    offset: params.offset,
    sort: params.sort,
    q: params.q,
  };
  const usp = new URLSearchParams(buildQuery(base).replace(/^\?/, ''));
  if (params.filters) {
    for (const [col, val] of Object.entries(params.filters)) {
      if (val === '' || val == null) continue;
      usp.append(`filter.${col}`, val);
    }
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : '';
}

export const dbApi = {
  tables: () => get<DbTablesResponse>('/v1/db/tables'),
  schema: (table: string) =>
    get<DbSchemaResponse>(`/v1/db/tables/${encodeURIComponent(table)}/schema`),
  rows: (table: string, params: DbRowsParams) =>
    get<DbRowsResponse>(
      `/v1/db/tables/${encodeURIComponent(table)}${dbRowsQuery(params)}`,
    ),
  exportCsvUrl: (table: string, params: Omit<DbRowsParams, 'limit' | 'offset'>) =>
    apiUrl(
      `/v1/db/tables/${encodeURIComponent(table)}/export.csv${dbRowsQuery(params)}`,
    ),
};

/* ------------------------------ users -------------------------------- */

export const usersApi = {
  list: (query: string, page: number, size: number) =>
    get<PageResponse<UserListItem>>(
      `/v1/users${buildQuery({ query, page, size })}`,
    ),
  detail: (id: string | number) =>
    get<UserDetail>(`/v1/users/${encodeURIComponent(String(id))}`),
};

/* ------------------------------- jobs -------------------------------- */

export const jobsApi = {
  stats: () => get<JobsStats>('/v1/jobs/stats'),
  list: (status: string, page: number, size: number) =>
    get<PageResponse<JobItem>>(
      `/v1/jobs${buildQuery({ status: status || undefined, page, size })}`,
    ),
  dlq: (limit: number) => get<DlqItem[]>(`/v1/jobs/dlq${buildQuery({ limit })}`),
};

/* ----------------------------- actions ------------------------------- */

export type KmaWhich = 'short' | 'mid' | 'housekeep';

export interface ZonePayload {
  name: string;
  reason?: string;
  geometry: unknown;
}

export const actionsApi = {
  kmaRunNow: (which: KmaWhich) =>
    post<KmaRunResult>(`/v1/actions/kma/run-now${buildQuery({ which })}`),
  patchGrid: (gridId: number | string, isActive: boolean) =>
    patch<GridPatchResult>(
      `/v1/actions/grids/${encodeURIComponent(String(gridId))}`,
      { is_active: isActive },
    ),
  listZones: () => get<ForbiddenZone[]>('/v1/actions/forbidden-zones'),
  createZone: (payload: ZonePayload) =>
    post<ForbiddenZone>('/v1/actions/forbidden-zones', payload),
  updateZone: (id: number | string, payload: ZonePayload) =>
    put<ForbiddenZone>(
      `/v1/actions/forbidden-zones/${encodeURIComponent(String(id))}`,
      payload,
    ),
  deleteZone: (id: number | string) =>
    del<ZoneDeleteResult>(
      `/v1/actions/forbidden-zones/${encodeURIComponent(String(id))}`,
    ),
  dlqReprocess: (ids: string[]) =>
    post<DlqActionResult>('/v1/actions/dlq/reprocess', { ids }),
  dlqDiscard: (ids: string[]) =>
    post<DlqActionResult>('/v1/actions/dlq/discard', { ids }),
};

/* ------------------------------ audit -------------------------------- */

export interface AuditParams {
  actor?: string;
  action?: string;
  from?: string;
  to?: string;
  limit: number;
  offset: number;
}

export const auditApi = {
  list: (params: AuditParams) =>
    get<AuditResponse>(`/v1/audit${buildQuery({ ...params })}`),
};
