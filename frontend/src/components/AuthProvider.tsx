import { ReactNode } from 'react';
import { useAccountQuery } from '@/evennia_replacements/queries';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Mounted once at the app root — the sole call site of `useAccountQuery()`.
 * That single mount is why the hydration effect lives inside the hook itself
 * rather than here: every hard reload runs this component before any route,
 * so `GET /api/user/`'s `selected_entry` reaches `gameSlice` (via
 * `hydrateActiveCharacter`, #3412) as early as the account fetch itself
 * resolves — no separate wiring needed per page.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  useAccountQuery();

  return <>{children}</>;
}
