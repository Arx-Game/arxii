import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchAccount, fetchRegistrationStatus, postLogin, postLogout, postRegister } from './api';
import { AccountData } from './types';
import { useAppDispatch } from '@/store/hooks';
import { setAccount } from '@/store/authSlice';
import { resetGame, hydrateActiveCharacter } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useEffect } from 'react';

export function useAccountQuery() {
  const dispatch = useAppDispatch();
  const result = useQuery({
    queryKey: ['account'],
    queryFn: fetchAccount,
    throwOnError: true,
  });

  useEffect(() => {
    // `undefined` means the query hasn't resolved yet (still pending) —
    // don't touch either slice until there's a real payload (which may
    // itself be `null`, meaning "no account": see fetchAccount's empty-body
    // case). `result.data` resolving to `null` also runs the hydrate branch
    // below, correctly clearing gameSlice — useLogout separately dispatches
    // resetGame() for the explicit-logout path, so this is belt-and-suspenders
    // for any other route that lands `data: null` (e.g. a stale/expired session).
    if (result.data === undefined) {
      return;
    }
    const account = result.data;
    dispatch(setAccount(account));
    // Reload survival (#3412): mirror the durable server-side selection into
    // gameSlice on every successful account fetch — hard reload -> this
    // fetch -> hydration -> IC-scoped pages (tidings, own-sheet) that read
    // `gameSlice.active` stop degrading. #3412 review fix: this now mirrors
    // BOTH directions — a `selected_entry` SETS active/activeEntryId, and its
    // absence (including `account === null`, the logged-out/no-account case)
    // CLEARS them (e.g. after `useSelectCharacterMutation.mutate(null)` + the
    // account refetch it triggers) — see `hydrateActiveCharacter`'s own doc
    // comment for why clearing the mirror is safe (never tears down a live
    // session; selection isn't presence in either direction). `entry` is
    // hoisted out (rather than narrowing `account.selected_entry` inline) so
    // the `account === null` case falls through the same `?? null` path
    // instead of needing its own branch.
    const entry = account?.selected_entry ?? null;
    dispatch(hydrateActiveCharacter(entry ? { name: entry.name, entryId: entry.id } : null));
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

/**
 * Whether registration is currently open (#3054). Public/unauthenticated.
 * Callers should treat a still-loading or errored fetch as "don't know" —
 * RegisterPage only shows the invite-only notice on an explicit `open: false`,
 * never while this query is pending, so a slow/failed status check doesn't
 * block the signup form from rendering.
 */
export function useRegistrationStatus() {
  return useQuery({
    queryKey: ['registrationStatus'],
    queryFn: fetchRegistrationStatus,
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
