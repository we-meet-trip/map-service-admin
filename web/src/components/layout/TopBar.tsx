import { useState } from 'react';
import { useAuth } from '../../providers/AuthProvider';
import { ThemeToggle } from '../ThemeToggle';
import { Spinner } from '../Spinner';
import { IconLogout } from '../Icons';

interface TopBarProps {
  onOpenMenu: () => void;
}

function MenuButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="btn btn-ghost btn-sm !px-2 lg:hidden"
      aria-label="메뉴 열기"
    >
      <svg
        width={20}
        height={20}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        aria-hidden="true"
      >
        <path d="M4 7h16M4 12h16M4 17h16" />
      </svg>
    </button>
  );
}

export function TopBar({ onOpenMenu }: TopBarProps) {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } catch {
      setLoggingOut(false);
    }
  }

  const initial = user?.username?.charAt(0)?.toUpperCase() ?? '?';

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-border bg-surface px-4">
      <MenuButton onClick={onOpenMenu} />
      <div className="flex-1" />
      <ThemeToggle />
      <div className="hidden items-center gap-2 rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 sm:flex">
        <span
          className="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-xs font-semibold text-brand-fg"
          aria-hidden="true"
        >
          {initial}
        </span>
        <span className="text-sm font-medium text-fg">
          {user?.username ?? '—'}
        </span>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        disabled={loggingOut}
        className="btn btn-ghost btn-sm"
      >
        {loggingOut ? <Spinner size={14} /> : <IconLogout width={16} height={16} />}
        <span className="hidden sm:inline">로그아웃</span>
      </button>
    </header>
  );
}
