import { useQuery, useMutation } from '@tanstack/react-query';
import {
  fetchHomeStats,
  fetchAccount,
  postLogin,
  postLogout,
  fetchRosterEntry,
  fetchMyRosterEntries,
  postRosterApplication,
} from './api';
import { useAppDispatch } from '../store/hooks';
import { setAccount } from '../store/authSlice';
import { useEffect } from 'react';

export function useHomeStatsQuery() {
  return useQuery({ queryKey: ['homepage'], queryFn: fetchHomeStats });
}

export function useAccountQuery() {
  const dispatch = useAppDispatch();
  const result = useQuery({
    queryKey: ['account'],
    queryFn: fetchAccount,
  });

  useEffect(() => {
    if (result.data !== undefined) {
      dispatch(setAccount(result.data));
    }
  }, [result.data, dispatch]);

  return result;
}

export function useLogin(onSuccess?: () => void) {
  const dispatch = useAppDispatch();
  return useMutation({
    mutationFn: postLogin,
    onSuccess: (data) => {
      dispatch(setAccount(data));
      onSuccess?.();
    },
  });
}

export function useLogout(onSuccess?: () => void) {
  const dispatch = useAppDispatch();
  return useMutation({
    mutationFn: postLogout,
    onSuccess: () => {
      dispatch(setAccount(null));
      onSuccess?.();
    },
  });
}

export function useRosterEntryQuery(id: number) {
  return useQuery({
    queryKey: ['roster-entry', id],
    queryFn: () => fetchRosterEntry(id),
    enabled: !!id,
  });
}

export function useMyRosterEntriesQuery(enabled = true) {
  return useQuery({
    queryKey: ['my-roster-entries'],
    queryFn: fetchMyRosterEntries,
    enabled,
  });
}

export function useSendRosterApplication(id: number) {
  return useMutation({
    mutationFn: (message: string) => postRosterApplication(id, message),
  });
}
