/** React Query hooks for the Account tab (#3591). Successful credential changes refresh ['account']. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import {
  ReauthenticationRequiredError,
  activateTotp,
  cancelEmailChange,
  changePassword,
  deactivateTotp,
  fetchAuthenticators,
  fetchEmailAddresses,
  fetchRecoveryCodes,
  fetchSecuritySettings,
  regenerateRecoveryCodes,
  requestEmailChange,
  resendEmailChangeVerification,
  setBlockTelnetLoginWith2fa,
} from './api';

export const emailKey = ['account', 'emails'] as const;
export const authenticatorsKey = ['account', 'authenticators'] as const;
export const securityKey = ['account', 'security-settings'] as const;

export function useEmailAddresses() {
  return useQuery({ queryKey: emailKey, queryFn: fetchEmailAddresses });
}

export function useAuthenticators() {
  return useQuery({ queryKey: authenticatorsKey, queryFn: fetchAuthenticators });
}

export function useSecuritySettings() {
  return useQuery({ queryKey: securityKey, queryFn: fetchSecuritySettings });
}

/** Recovery codes are fetched on demand and never kept in the cache. */
export function useRecoveryCodes(enabled: boolean) {
  return useQuery({
    queryKey: ['account', 'recovery-codes'],
    queryFn: fetchRecoveryCodes,
    enabled,
    gcTime: 0,
    staleTime: 0,
  });
}

function useInvalidate(keys: readonly (readonly string[])[]) {
  const queryClient = useQueryClient();
  return () => keys.forEach((k) => queryClient.invalidateQueries({ queryKey: [...k] }));
}

export function useRequestEmailChange() {
  const invalidate = useInvalidate([emailKey, ['account']]);
  return useMutation({ mutationFn: requestEmailChange, onSuccess: invalidate });
}
export function useResendEmailChange() {
  return useMutation({ mutationFn: resendEmailChangeVerification });
}
export function useCancelEmailChange() {
  const invalidate = useInvalidate([emailKey]);
  return useMutation({ mutationFn: cancelEmailChange, onSuccess: invalidate });
}
export function useChangePassword() {
  const invalidate = useInvalidate([['account']]);
  return useMutation({ mutationFn: changePassword, onSuccess: invalidate });
}
export function useActivateTotp() {
  const invalidate = useInvalidate([authenticatorsKey]);
  return useMutation({ mutationFn: activateTotp, onSuccess: invalidate });
}
export function useDeactivateTotp() {
  const invalidate = useInvalidate([authenticatorsKey, securityKey]);
  return useMutation({ mutationFn: deactivateTotp, onSuccess: invalidate });
}
export function useRegenerateRecoveryCodes() {
  const invalidate = useInvalidate([authenticatorsKey]);
  return useMutation({ mutationFn: regenerateRecoveryCodes, onSuccess: invalidate });
}
export function useSetBlockTelnet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: setBlockTelnetLoginWith2fa,
    onSuccess: (data) => queryClient.setQueryData([...securityKey], data),
  });
}

export interface ReauthDialogProps {
  open: boolean;
  flows: string[];
  onSuccess: () => void;
  onCancel: () => void;
}

interface Waiter {
  resolve: () => void;
  reject: (e: unknown) => void;
}

/**
 * Wrap a sensitive call: on a reauthentication challenge, open the dialog, and once the
 * player has confirmed, retry the original call exactly once.
 *
 * Multiple calls can overlap while the dialog is open (a second `run()` arrives before the
 * first one's confirmation): every overlapping caller registers its own waiter, and a single
 * `onSuccess()` resolves (or `onCancel()` rejects) all of them, each then retrying its own
 * call once.
 */
export function useReauthGuard() {
  const [open, setOpen] = useState(false);
  const [flows, setFlows] = useState<string[]>([]);
  const waiters = useRef<Waiter[]>([]);

  async function attempt<T>(fn: () => Promise<T>): Promise<T> {
    try {
      return await fn();
    } catch (error) {
      if (!(error instanceof ReauthenticationRequiredError)) throw error;
      setFlows((prev) => Array.from(new Set([...prev, ...error.flows])));
      setOpen(true);
      await new Promise<void>((resolve, reject) => {
        waiters.current.push({ resolve, reject });
      });
      return await fn();
    }
  }

  const run = useCallback(<T>(fn: () => Promise<T>): Promise<T> => attempt(fn), []);

  function settleAll(fn: (waiter: Waiter) => void) {
    setOpen(false);
    const toSettle = waiters.current;
    waiters.current = [];
    toSettle.forEach(fn);
  }

  const dialogProps: ReauthDialogProps = {
    open,
    flows,
    onSuccess: () => settleAll((waiter) => waiter.resolve()),
    onCancel: () => settleAll((waiter) => waiter.reject(new Error('Cancelled.'))),
  };

  return { run, dialogProps };
}
