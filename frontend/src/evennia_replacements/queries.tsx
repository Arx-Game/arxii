import { useQuery, useMutation } from '@tanstack/react-query'
import { fetchHomeStats, fetchAccount, postLogin, postLogout } from './api'
import { useAppDispatch } from '../store/hooks'
import { setAccount } from '../store/authSlice'

export function useHomeStats() {
  return useQuery({ queryKey: ['homepage'], queryFn: fetchHomeStats })
}

export function useAccountQuery() {
  const dispatch = useAppDispatch()
  return useQuery({
    queryKey: ['account'],
    queryFn: fetchAccount,
    onSuccess: (data) => {
      dispatch(setAccount(data))
    },
  })
}

export function useLogin(onSuccess?: () => void) {
  const dispatch = useAppDispatch()
  return useMutation({
    mutationFn: postLogin,
    onSuccess: (data) => {
      dispatch(setAccount(data))
      onSuccess?.()
    },
  })
}

export function useLogout(onSuccess?: () => void) {
  const dispatch = useAppDispatch()
  return useMutation({
    mutationFn: postLogout,
    onSuccess: () => {
      dispatch(setAccount(null))
      onSuccess?.()
    },
  })
}
