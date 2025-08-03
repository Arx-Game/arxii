import type { AccountData, HomeStats } from './types'

function getCSRFToken(): string {
  return (
    document.cookie
      .split('; ')
      .find((row) => row.startsWith('csrftoken='))
      ?.split('=')[1] || ''
  )
}

export async function fetchHomeStats(): Promise<HomeStats> {
  const res = await fetch('/api/homepage/')
  if (!res.ok) {
    throw new Error('Failed to load stats')
  }
  return res.json()
}

export async function fetchAccount(): Promise<AccountData | null> {
  const res = await fetch('/api/login/', { credentials: 'include' })
  if (!res.ok) {
    throw new Error('Failed to load account')
  }
  return res.json()
}

export async function postLogin(data: {
  username: string
  password: string
}): Promise<AccountData> {
  const res = await fetch('/api/login/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCSRFToken(),
    },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error('Login failed')
  }
  return res.json()
}

export async function postLogout(): Promise<void> {
  await fetch('/api/logout/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCSRFToken() },
    credentials: 'include',
  })
}
