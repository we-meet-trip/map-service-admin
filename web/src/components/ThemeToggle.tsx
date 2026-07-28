import { useTheme } from '../providers/ThemeProvider';
import { IconMoon, IconSun } from './Icons';

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === 'dark';
  return (
    <button
      type="button"
      onClick={toggle}
      className="btn btn-ghost btn-sm h-9 w-9 !px-0"
      aria-label={isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}
      title={isDark ? '라이트 모드' : '다크 모드'}
    >
      {isDark ? <IconSun /> : <IconMoon />}
    </button>
  );
}
