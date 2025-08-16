import { ReactNode } from 'react';
import { useAccountQuery } from '@/evennia_replacements/queries';

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  useAccountQuery();

  return <>{children}</>;
}
