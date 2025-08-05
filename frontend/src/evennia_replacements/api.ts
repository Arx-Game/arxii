import type { AccountData, HomeStats, RosterEntryData, MyRosterEntry } from './types';

function getCSRFToken(): string {
  return (
    document.cookie
      .split('; ')
      .find((row) => row.startsWith('csrftoken='))
      ?.split('=')[1] || ''
  );
}

function apiFetch(url: string, options: RequestInit = {}) {
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

export async function fetchRosterEntry(id: number): Promise<RosterEntryData> {
  const res = await apiFetch(`/api/roster/${id}/`);
  if (!res.ok) {
    throw new Error('Failed to load roster entry');
  }
  return res.json();
}

export async function fetchMyRosterEntries(): Promise<MyRosterEntry[]> {
  const res = await apiFetch('/api/roster/mine/');
  if (!res.ok) {
    throw new Error('Failed to load characters');
  }
  return res.json();
}

export async function postRosterApplication(id: number, message: string): Promise<void> {
  const res = await apiFetch(`/api/roster/${id}/apply/`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    throw new Error(`Failed to send application for character ${id}`);
  }
}
