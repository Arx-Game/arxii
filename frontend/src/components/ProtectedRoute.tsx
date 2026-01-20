import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';

interface ProtectedRouteProps {
  children: ReactNode;
}

/**
 * Route guard that redirects unauthenticated users to the login page.
 * Used to protect pages that require authentication.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const account = useAppSelector((state) => state.auth.account);

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
