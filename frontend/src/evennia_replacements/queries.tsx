import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchStatus, fetchAccount, postLogin, postLogout, postRegister } from './api';
import { AccountData } from './types';
import { useAppDispatch } from '@/store/hooks';
import { setAccount } from '@/store/authSlice';
import { resetGame } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useEffect } from 'react';

export function useStatusQuery() {
  return useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 30000,
    throwOnError: true,
  });
}

export function useAccountQuery() {
  const dispatch = useAppDispatch();
  const result = useQuery({
    queryKey: ['account'],
    queryFn: fetchAccount,
    throwOnError: true,
  });

  useEffect(() => {
    if (result.data !== undefined) {
      dispatch(setAccount(result.data));
    }
  }, [result.data, dispatch]);

  return result;
}

/**
 * Subscribe to the in-flight state of the account query — used by route
 * guards (StaffRoute, ProtectedRoute, GuestOnlyRoute) to avoid the
 * "direct URL navigation race": on a hard page load Redux starts with
 * `account = null`, and a guard reading Redux immediately would fire a
 * redirect before useAccountQuery's fetch resolves. The guard reads
 * `isPending` here, defers the redirect decision until the fetch
 * settles, and only then trusts the Redux account value.
 *
 * Shares the `['account']` query key with `useAccountQuery`, so React
 * Query dedupes — no extra network request, no double dispatch.
 */
export function useIsAccountLoading() {
  const { isPending } = useQuery({
    queryKey: ['account'],
    queryFn: fetchAccount,
  });
  return isPending;
}

export function useLogin(onSuccess?: (data: AccountData) => void) {
  const dispatch = useAppDispatch();
  return useMutation({
    mutationFn: postLogin,
    onSuccess: (data) => {
      dispatch(setAccount(data));
      onSuccess?.(data);
    },
  });
}

export function useRegister(
  onSuccess?: (result: { success: true; emailVerificationRequired: boolean }, email: string) => void
) {
  return useMutation({
    mutationFn: postRegister,
    onSuccess: (result, variables) => {
      // User will need to log in after email verification
      onSuccess?.(result, variables.email);
    },
  });
}

export function useLogout(onSuccess?: () => void) {
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  const { disconnectAll } = useGameSocket();
  return useMutation({
    mutationFn: postLogout,
    onSuccess: () => {
      disconnectAll();
      dispatch(resetGame());
      dispatch(setAccount(null));
      queryClient.clear();
      onSuccess?.();
    },
  });
}
