import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get, post, patch, selectedEnvironment } from '../api/client';
import { useAuth } from '../providers/AuthProvider';
import { PageHeader } from '../components/PageHeader';
import { ErrorBanner } from '../components/ErrorBanner';

type Role = 'owner' | 'operator' | 'viewer';
interface Operator { id: number; username: string; role: Role; is_active: boolean; allowed_environments: string[] }

export function OperatorsPage() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const rows = useQuery({ queryKey: ['operators'], enabled: user?.role === 'owner',
    queryFn: () => get<{ items: Operator[] }>('/v1/operators') });
  const targets = useQuery({ queryKey: ['environments'],
    queryFn: () => get<{ environments: string[] }>('/v1/environments') });
  const [editing, setEditing] = useState<Operator | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role>('viewer');
  const [environments, setEnvironments] = useState<string[]>([selectedEnvironment()]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function edit(row: Operator | null) {
    setEditing(row); setUsername(row?.username ?? ''); setPassword('');
    setRole(row?.role ?? 'viewer');
    setEnvironments(row?.allowed_environments ?? [selectedEnvironment()]);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const body = { role, environments, active: editing?.is_active ?? true,
        ...(password ? { password } : {}) };
      if (editing) await patch(`/v1/operators/${editing.id}`, body);
      else await post('/v1/operators', { ...body, username });
      edit(null); await cache.invalidateQueries({ queryKey: ['operators'] });
    } catch (err) { setError(err); }
    finally { setPassword(''); setBusy(false); }
  }

  async function toggle(row: Operator) {
    if (!window.confirm(`${row.username} 계정을 ${row.is_active ? '비활성화하고 모든 세션을 종료' : '활성화'}할까요?`)) return;
    setBusy(true); setError(null);
    try {
      await patch(`/v1/operators/${row.id}`, { role: row.role,
        environments: row.allowed_environments, active: !row.is_active });
      await cache.invalidateQueries({ queryKey: ['operators'] });
    } catch (err) { setError(err); }
    finally { setBusy(false); }
  }

  if (user?.role !== 'owner') return <p>소유자 계정만 운영자를 관리할 수 있습니다.</p>;
  return <div className="space-y-5">
    <PageHeader title="운영자 계정" />
    <p className="text-sm text-fg-muted">권한·비밀번호 변경과 비활성화는 해당 계정의 모든 세션을 종료합니다. 계정과 감사 이력은 삭제하지 않습니다.</p>
    {(error || rows.error) ? <ErrorBanner error={error || rows.error} /> : null}
    <div className="overflow-x-auto rounded border border-border">
      <table className="w-full text-left text-sm"><thead><tr>
        <th className="p-3">계정</th><th>역할</th><th>환경</th><th>상태</th><th>관리</th>
      </tr></thead><tbody>{rows.data?.items.map((row) => <tr key={row.id} className="border-t border-border">
        <td className="p-3">{row.username}</td><td>{row.role}</td>
        <td>{row.role === 'owner' ? '전체' : row.allowed_environments.join(', ')}</td>
        <td>{row.is_active ? '활성' : '비활성'}</td>
        <td><button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => edit(row)}>수정</button>
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void toggle(row)}>{row.is_active ? '비활성화' : '활성화'}</button></td>
      </tr>)}</tbody></table>
    </div>
    <form onSubmit={(event) => void save(event)} className="max-w-xl space-y-3 rounded border border-border bg-surface p-4">
      <p className="font-semibold">{editing ? `${editing.username} 수정` : '개인 계정 추가'}</p>
      <label className="block">계정 이름<input className="mt-1 block w-full rounded border border-border bg-bg p-2" value={username} disabled={!!editing} required pattern="[A-Za-z0-9_.@-]{1,100}" onChange={(e) => setUsername(e.target.value)} autoComplete="off" /></label>
      <label className="block">{editing ? '새 비밀번호 (변경할 때만)' : '비밀번호'}<input type="password" className="mt-1 block w-full rounded border border-border bg-bg p-2" value={password} required={!editing} minLength={12} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></label>
      <label className="block">역할<select className="ml-2 rounded border border-border bg-bg p-2" value={role} onChange={(e) => setRole(e.target.value as Role)}>
        <option value="viewer">조회</option><option value="operator">운영 작업</option><option value="owner">소유자·계정 관리</option>
      </select></label>
      <fieldset><legend>접근할 환경 {role === 'owner' ? '(소유자는 전체 접근)' : ''}</legend>
        {targets.data?.environments.map((name) => <label key={name} className="mr-4 inline-flex items-center gap-2"><input type="checkbox" checked={environments.includes(name)} onChange={(e) => setEnvironments(e.target.checked ? [...environments, name] : environments.filter((n) => n !== name))} />{name}</label>)}
      </fieldset>
      <button className="btn btn-primary" disabled={busy} type="submit">{busy ? '저장 중…' : '저장'}</button>
      {editing && <button className="btn btn-ghost" type="button" onClick={() => edit(null)}>취소</button>}
    </form>
  </div>;
}
