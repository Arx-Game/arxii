import { useQuery, useMutation } from '@tanstack/react-query'
import { fetchHomeStats, fetchLoginContext, postLogin } from '@/evennia_replacements/api'
import type { AccountData } from '@/evennia_replacements/types'

export function useHomeStats() {
  return useQuery({ queryKey: ['homepage'], queryFn: fetchHomeStats })
}

export function useLoginContext() {
  return useQuery({ queryKey: ['loginContext'], queryFn: fetchLoginContext })
}

export function useLogin(onSuccess: (user: AccountData) => void) {
  return useMutation({
    mutationFn: postLogin,
    onSuccess: (data) => {
      if (data.user) onSuccess(data.user)
    },
  })
}
