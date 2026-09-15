import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  completeMfaLogin,
  fetchAccount,
  fetchRegistrationStatus,
  postLogin,
  postLogout,
  postRegister,
} from './api';
import { AccountData, LoginResult } from './types';
import { useStore } from 'react-redux';
import type { RootState } from '@/store/store';
import { useAppDispatch } from '@/store/hooks';
import { setAccount } from '@/store/authSlice';
import {
  resetGame,
  hydrateActiveCharacter,
  setBrowsingIdentity,
  clearBrowsingIdentity,
} from '@/store/gameSlice';
import { readTabIdentity, writeTabIdentity, clearTabIdentity } from '@/store/browsingIdentity';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function useAccountQuery() {
  const dispatch = useAppDispatch();
  // The store handle, NOT a selector: the effect below reads Redux's own idea
  // of this tab's browsing identity at run time (so a cold-Redux/warm-storage
  // mismatch after a reload is detected and repaired, #3479 review round 1),
  // but a Redux-only change must never re-run the effect. With the value in
  // the deps, the Hall's "Clear Active Character" (clearBrowsingIdentity)
  // re-ran it against the CACHED account, whose selected_entry still named
  // the old character, and the seed branch wrote that character straight
  // back before the clearing mutation's refetch could land (whole-branch
  // review, Critical). The effect keys on `result.data` alone.
  const store = useStore<RootState>();
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
    // Reload survival (#3412) + per-tab browsing identity (#3479): mirror the
    // durable server-side selection into gameSlice, but only SEED this tab's
    // identity -- never overwrite it once this tab has one. Before #3479
    // this ran unconditionally on every account refetch, which is exactly
    // the cross-tab stomp bug: Tab A puppeting character X would have its
    // `active` silently rewritten the moment Tab B's (or the Hall's)
    // selection change invalidated the shared `['account']` query and Tab
    // A's own refetch (e.g. on window focus) mirrored it in. `entry` is
    // hoisted out (rather than narrowing `account.selected_entry` inline) so
    // the `account === null` case (logged out/no account) falls through the
    // same `?? null` path instead of needing its own branch.
    const entry = account?.selected_entry ?? null;
    const stored = readTabIdentity();

    if (stored !== null) {
      // "Owned" here means "appears in the account's ACTIVE roster today"
      // (`available_characters` -- same list the Hall picker docks avatars
      // from), not literal FK ownership: a retired/archived entry drops out
      // of this list even though the account row still technically exists.
      // That is exactly the case this branch's fallthrough (clear + reseed)
      // is for.
      const ownedIds = account?.available_characters.map((c) => c.id) ?? [];
      if (ownedIds.includes(stored.entryId)) {
        // This tab already has a browsing identity it still owns. Gate the
        // dispatch on REDUX's own state, not on storage presence alone
        // (#3479 review round 1): after a hard reload, sessionStorage
        // survives but Redux starts cold (`browsingEntryId`/`active` both
        // null), so a bare early return here would leave the tab showing no
        // selection at all despite a perfectly valid stored identity. Only
        // when Redux is already in sync do we truly no-op -- that's what
        // keeps a later refetch carrying a DIFFERENT account default from
        // overwriting an already-hydrated tab (never tears down a live
        // session either way; selection isn't presence).
        if (store.getState().game.browsingEntryId !== stored.entryId) {
          const ownedEntry = account?.available_characters.find((c) => c.id === stored.entryId);
          dispatch(setBrowsingIdentity(stored.entryId));
          if (ownedEntry) {
            dispatch(hydrateActiveCharacter({ name: ownedEntry.name, entryId: stored.entryId }));
          }
        }
        return;
      }
      // The stored entry is no longer among this account's entries (e.g. the
      // character was retired) -- treat this tab as fresh and reseed below.
      clearTabIdentity();
    }

    // First hydration of this tab (or a stale identity just cleared above):
    // seed from the account's durable default, same full-overwrite hydration
    // this always did before #3479, plus writing this tab's own store so a
    // later refetch in THIS tab hits the early return above instead.
    if (entry) {
      writeTabIdentity(entry.id);
      dispatch(setBrowsingIdentity(entry.id));
    } else {
      dispatch(clearBrowsingIdentity());
    }
    dispatch(hydrateActiveCharacter(entry ? { name: entry.name, entryId: entry.id } : null));
  }, [result.data, dispatch, store]);

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

export function useLogin(onSuccess?: (data: LoginResult) => void) {
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postLogin,
    onSuccess: (data) => {
      if (data.kind === 'ok') {
        // Keep React Query cache in sync with Redux so guards reading the
        // cache (via useAuthStatus) see the authenticated state on the
        // next render — without this, post-login navigation to a guarded
        // route would bounce back through /login because the cache still
        // showed `data: null` from the pre-login fetch.
        queryClient.setQueryData(['account'], data.account);
        dispatch(setAccount(data.account));
      }
      onSuccess?.(data);
    },
  });
}

/** Completes a login that stopped at the 2FA step (#3591). Same cache/Redux
 * write-through as the `useLogin` ok branch, once the code is accepted. */
export function useCompleteMfaLogin(onSuccess?: (account: AccountData) => void) {
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: completeMfaLogin,
    onSuccess: (account) => {
      queryClient.setQueryData(['account'], account);
      dispatch(setAccount(account));
      onSuccess?.(account);
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

/**
 * Log out and land on the logged-out home page, whatever page is open (#3592).
 *
 * Clearing the cache alone does NOT leave the current page. Most routes
 * (e.g. /characters/create) have no guard at all, so nothing would ever
 * move them. On a guarded route the guard keeps its last observer result
 * until something re-renders it, and nothing it subscribes to changes when
 * the `['account']` entry is removed, so it stayed put too; and even when
 * a guard did re-evaluate, its destination (`/login`) is wrong for a
 * deliberate logout. Hence this hook navigates to `/` itself, and writes
 * `null` into `['account']` so every reader (guards, GatefoldPage) sees a
 * settled logged-out account instead of a pending refetch.
 */
export function useLogout(onSuccess?: () => void) {
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { disconnectAll } = useGameSocket();
  return useMutation({
    mutationFn: postLogout,
    onSuccess: () => {
      disconnectAll();
      dispatch(resetGame());
      dispatch(setAccount(null));
      // clear() drops every per-account cache entry (mail, roster, ...)
      // so the next login never sees the previous account's data.
      queryClient.clear();
      queryClient.setQueryData(['account'], null);
      navigate('/');
      onSuccess?.();
    },
  });
}
