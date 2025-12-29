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
