import type { StatusLevel } from '../components/StatusPill';
import type { HealthItem } from '../api/types';

/** Map a health probe to a status level (colour + label pairing lives in the pill). */
export function healthLevel(item: HealthItem): StatusLevel {
  if (item.configured === false) return 'unknown';
  if (item.ok) return 'ok';
  return 'down';
}

/** Map job status strings to a badge tone. */
export function jobStatusTone(
  status: string,
): 'good' | 'warn' | 'critical' | 'brand' | 'neutral' {
  const s = status.toLowerCase();
  if (s === 'done' || s === 'success' || s === 'completed') return 'good';
  if (s === 'in_progress' || s === 'running' || s === 'pending') return 'brand';
  if (s === 'failed' || s === 'error' || s === 'dead') return 'critical';
  return 'neutral';
}
