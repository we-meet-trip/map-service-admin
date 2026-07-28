import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/endpoints';
import { ME_QUERY_KEY, useAuth } from '../providers/AuthProvider';
import { errorMessage } from '../components/ErrorBanner';
import { Spinner } from '../components/Spinner';
import { ThemeToggle } from '../components/ThemeToggle';
import { IconAlert } from '../components/Icons';

interface LocationState {
  from?: string;
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { user, isLoading } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const redirectTo = (location.state as LocationState | null)?.from ?? '/';

  const loginMutation = useMutation({
    mutationFn: () => authApi.login(username.trim(), password),
    onSuccess: (data) => {
      queryClient.setQueryData(ME_QUERY_KEY, data);
      navigate(redirectTo, { replace: true });
    },
  });

  // Already authenticated — skip the form.
  if (user && !loginMutation.isPending) {
    return <Navigate to={redirectTo} replace />;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) return;
    loginMutation.mutate();
  }

  const busy = loginMutation.isPending || (isLoading && !user);

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand text-lg font-bold text-brand-fg">
            M
          </span>
          <div>
            <h1 className="text-lg font-semibold text-fg">MAP 운영 콘솔</h1>
            <p className="mt-1 text-sm text-fg-muted">
              운영자 계정으로 로그인하세요
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4 p-6">
          {loginMutation.isError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-critical bg-critical-weak px-3 py-2 text-xs text-critical"
            >
              <IconAlert width={16} height={16} className="mt-0.5 shrink-0" />
              <span>{errorMessage(loginMutation.error)}</span>
            </div>
          )}

          <div>
            <label className="label" htmlFor="username">
              사용자명
            </label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <div>
            <label className="label" htmlFor="password">
              비밀번호
            </label>
            <input
              id="password"
              type="password"
              className="input"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary w-full"
            disabled={busy || !username.trim() || !password}
          >
            {busy && <Spinner size={16} />}
            로그인
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-fg-subtle">
          세션 쿠키(admin_session)로 인증됩니다.
        </p>
      </div>
    </div>
  );
}
