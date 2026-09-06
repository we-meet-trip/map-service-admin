/**
 * Single fetch wrapper for the admin API.
 *
 * - Every request sends the session cookie (`credentials: 'include'`).
 * - A 401 triggers the registered unauthorized handler (redirect to /login).
 * - Non-2xx responses throw `ApiError` carrying the parsed body/message.
 */

const API_BASE = '/api';

export function selectedEnvironment(): string {
  return sessionStorage.getItem('map.environment') ?? 'test';
}

export function selectEnvironment(name: string): void {
  sessionStorage.setItem('map.environment', name);
  // 진행 중인 조회와 캐시가 새 대상 화면에 섞이지 않게 새로 연다.
  window.location.reload();
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registered once by the app so the client can redirect on 401. */
export function setUnauthorizedHandler(fn: UnauthorizedHandler | null): void {
  unauthorizedHandler = fn;
}

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined
>;

/** Build a `?a=b&c=d` string, dropping null/undefined/empty values. */
export function buildQuery(params?: QueryParams): string {
  if (!params) return '';
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    usp.append(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : '';
}

/** Absolute API URL for a path — used for direct links (e.g. CSV export). */
export function apiUrl(path: string): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  url.searchParams.set('environment', selectedEnvironment());
  return `${url.pathname}${url.search}`;
}

async function parseBody(res: Response): Promise<unknown> {
  const contentType = res.headers.get('content-type') ?? '';
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined;
  }
  if (contentType.includes('application/json')) {
    try {
      return await res.json();
    } catch {
      return undefined;
    }
  }
  try {
    return await res.text();
  } catch {
    return undefined;
  }
}

function messageFromBody(status: number, body: unknown): string {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    const detail = record.detail ?? record.message ?? record.error;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail && typeof detail === 'object') {
      const nested = (detail as Record<string, unknown>).message;
      if (typeof nested === 'string') return nested;
    }
  }
  if (typeof body === 'string' && body.trim()) return body;
  return `요청이 실패했습니다 (HTTP ${status}).`;
}

interface RequestOptions {
  body?: unknown;
  signal?: AbortSignal;
  /** When true, a 401 will NOT trigger the global redirect (used by /auth/me). */
  silent401?: boolean;
}

async function request<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const environment = selectedEnvironment();
  const headers: Record<string, string> = {
    Accept: 'application/json', 'X-Map-Environment': environment,
  };
  const hasBody = options.body !== undefined;
  if (hasBody) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: 'include',
      headers,
      body: hasBody ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (err) {
    throw new ApiError(
      0,
      '서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요.',
      err,
    );
  }

  if (res.status === 401) {
    if (!options.silent401) unauthorizedHandler?.();
    const body = await parseBody(res);
    throw new ApiError(401, '인증이 필요합니다.', body);
  }

  const body = await parseBody(res);
  if (environment !== selectedEnvironment()) {
    throw new ApiError(409, '조회 대상이 변경됐습니다. 다시 확인하세요.', undefined);
  }
  if (!res.ok) {
    throw new ApiError(res.status, messageFromBody(res.status, body), body);
  }
  return body as T;
}

export function get<T>(
  path: string,
  opts?: { signal?: AbortSignal; silent401?: boolean },
): Promise<T> {
  return request<T>('GET', path, opts);
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, { body });
}

export function patch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('PATCH', path, { body });
}

export function put<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('PUT', path, { body });
}

export function del<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('DELETE', path, { body });
}
