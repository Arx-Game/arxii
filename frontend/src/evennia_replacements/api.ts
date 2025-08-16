import type { AccountData, StatusData } from './types';
import { getCookie } from '@/lib/utils';

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

export async function fetchStatus(): Promise<StatusData> {
  const res = await apiFetch('/api/status/');
  if (!res.ok) {
    throw new Error('Failed to load status');
  }
  return res.json();
}

export async function fetchAccount(): Promise<AccountData | null> {
  const res = await apiFetch('/api/login/');
  if (!res.ok) {
    throw new Error('Failed to load account');
  }

  const text = await res.text();
  if (!text.trim()) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    console.error('Failed to parse account response:', text);
    throw new Error('Invalid account response format');
  }
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

export async function postRegister(data: {
  username: string;
  password: string;
  email: string;
}): Promise<AccountData> {
  const res = await apiFetch('/api/register/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Registration failed');
  }
  return res.json();
}

export async function checkUsername(username: string): Promise<boolean> {
  const res = await apiFetch(
    `/api/register/availability/?username=${encodeURIComponent(username)}`
  );
  if (!res.ok) {
    throw new Error('Username check failed');
  }
  const data = await res.json();
  return data.username;
}

export async function checkEmail(email: string): Promise<boolean> {
  const res = await apiFetch(`/api/register/availability/?email=${encodeURIComponent(email)}`);
  if (!res.ok) {
    throw new Error('Email check failed');
  }
  const data = await res.json();
  return data.email;
}
