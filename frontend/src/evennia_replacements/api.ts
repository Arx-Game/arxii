import type { AccountData, HomeStats } from './types';
import { getCookie } from '../lib/utils';

function getCSRFToken(): string {
  return getCookie('csrftoken') || '';
}

export function apiFetch(url: string, options: RequestInit = {}) {
  const method = options.method?.toUpperCase() ?? 'GET';
  const headers = new Headers(options.headers);

  if (method !== 'GET') {
    headers.set('Content-Type', 'application/json');
    headers.set('X-CSRFToken', getCSRFToken());
  }

  return fetch(url, {
    credentials: 'include',
    ...options,
    headers,
  });
}

export async function fetchHomeStats(): Promise<HomeStats> {
  const res = await apiFetch('/api/homepage/');
  if (!res.ok) {
    throw new Error('Failed to load stats');
  }
  return res.json();
}

export async function fetchAccount(): Promise<AccountData | null> {
  const res = await apiFetch('/api/login/');
  if (!res.ok) {
    throw new Error('Failed to load account');
  }
  return res.json();
}

export async function postLogin(data: {
  username: string;
  password: string;
}): Promise<AccountData> {
  const res = await apiFetch('/api/login/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Login failed');
  }
  return res.json();
}

export async function postLogout(): Promise<void> {
  await apiFetch('/api/logout/', { method: 'POST' });
}
