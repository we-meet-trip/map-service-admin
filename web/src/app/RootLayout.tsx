import { Outlet } from 'react-router-dom';
import { AuthProvider } from '../providers/AuthProvider';

/**
 * Root of the routed tree. Lives inside the router so AuthProvider can use
 * navigation hooks and register the global 401 → /login handler.
 */
export function RootLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}
