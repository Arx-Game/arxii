import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/errors';

/**
 * Retry transient failures only. A 4xx is deterministic — retrying a 403/404
 * three times just triples the request load and adds ~seconds of spinner
 * before the same failure surfaces (and auth failures hammered the backend
 * exactly when the session was invalid). Only `ApiError` carries a status;
 * plain string-Errors from not-yet-migrated call sites keep the old policy.
 */
function retryTransientOnly(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: retryTransientOnly,
    },
  },
});
