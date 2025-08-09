import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchHomeStats, fetchAccount, postLogin, postLogout } from './api';
import { useAppDispatch } from '../store/hooks';
import { setAccount } from '../store/authSlice';
import { resetGame } from '../store/gameSlice';
import { useGameSocket } from '../hooks/useGameSocket';
import { useEffect } from 'react';

export function useHomeStatsQuery() {
  return useQuery({
    queryKey: ['homepage'],
    queryFn: fetchHomeStats,
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
