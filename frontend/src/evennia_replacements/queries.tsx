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
 * Auth state read by route guards (StaffRoute, ProtectedRoute,
 * GuestOnlyRoute) to avoid the direct-URL-navigation race.
 *
 * On hard page load Redux starts at `account: null` and useAccountQuery
 * fetches /api/user/ asynchronously, dispatching to Redux in a
 * useEffect AFTER the fetch resolves. That `useEffect`-after-render
 * gap created a render in which the React Query data was settled but
 * Redux was still null — so the guards (reading Redux) would fire a
 * Navigate to /login, and the GuestOnlyRoute on /login would see the
 * NEXT render with Redux populated and bounce the user to /. End
 * result: typing /staff/anything in the address bar always landed on
 * the home page.
 *
 * Fix: read both `isPending` and `data` from the same React Query
 * snapshot. They update atomically within a render, so the guards make
 * a consistent decision. Login mutations now also write through to the
 * React Query cache (see useLogin / useLogout below) so post-login
 * navigation works the same way.
 *
 * Shares the `['account']` query key with useAccountQuery, so React
 * Query dedupes — no extra request.
 */
export function useAuthStatus(): { isLoading: boolean; account: AccountData | null } {
  const { isPending, data } = useQuery({
    queryKey: ['account'],
    queryFn: fetchAccount,
  });
  return { isLoading: isPending, account: data ?? null };
}

export function useLogin(onSuccess?: (data: AccountData) => void) {
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postLogin,
    onSuccess: (data) => {
      // Keep React Query cache in sync with Redux so guards reading the
      // cache (via useAuthStatus) see the authenticated state on the
      // next render — without this, post-login navigation to a guarded
      // route would bounce back through /login because the cache still
      // showed `data: null` from the pre-login fetch.
      queryClient.setQueryData(['account'], data);
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
      // clear() wipes every cache entry including ['account']; that's
      // what guards observe as `isPending` flipping back true on the
      // next route — render `null`, then redirect to /login once the
      // cleared cache settles with `data: null`.
      queryClient.clear();
      onSuccess?.();
    },
  });
}
