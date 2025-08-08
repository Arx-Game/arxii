import type { RosterEntryData, MyRosterEntry, RosterData } from './types';
import type { PaginatedResponse } from '@/shared/types';
import { apiFetch } from '../evennia_replacements/api';

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

export async function fetchRosters(): Promise<RosterData[]> {
  const res = await apiFetch('/api/roster/rosters/');
  if (!res.ok) {
    throw new Error('Failed to load rosters');
  }
  return res.json();
}

export async function fetchRosterEntries(
  rosterId: number,
  page = 1,
  filters: { name?: string; class?: string; gender?: string } = {}
): Promise<PaginatedResponse<RosterEntryData>> {
  const params = new URLSearchParams({ roster: String(rosterId), page: String(page) });
  if (filters.name) params.set('name', filters.name);
  if (filters.class) params.set('class', filters.class);
  if (filters.gender) params.set('gender', filters.gender);
  const res = await apiFetch(`/api/roster/?${params.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to load roster entries');
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
