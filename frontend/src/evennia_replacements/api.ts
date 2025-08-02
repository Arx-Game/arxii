import type { AccountData, HomeStats, LoginContext } from '@/evennia_replacements/types'

export async function fetchHomeStats(): Promise<HomeStats> {
  const res = await fetch('/api/homepage/')
  if (!res.ok) {
    throw new Error('Failed to load stats')
  }
  return res.json()
}

export async function fetchLoginContext(): Promise<LoginContext> {
  const res = await fetch('/api/login/')
  if (!res.ok) {
    throw new Error('Failed to load login context')
  }
  return res.json()
}

export async function postLogin(data: {
  username: string
  password: string
}): Promise<{ success: boolean; user?: AccountData }> {
  const res = await fetch('/api/login/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    throw new Error('Login failed')
  }
  return res.json()
}
