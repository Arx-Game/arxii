import type { PlayerMail, MailFormData, RosterTenureOption } from './types';
import type { PaginatedResponse } from '@/shared/types';
import { apiFetch } from '@/evennia_replacements/api';

export async function fetchMail(page = 1): Promise<PaginatedResponse<PlayerMail>> {
  const res = await apiFetch(`/api/roster/mail/?page=${page}`);
  if (!res.ok) {
    throw new Error('Failed to load mail');
  }
  return res.json();
}

export async function sendMail(data: MailFormData): Promise<void> {
  const res = await apiFetch('/api/roster/mail/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to send mail');
  }
}

export async function searchTenures(term: string): Promise<PaginatedResponse<RosterTenureOption>> {
  const res = await apiFetch(`/api/roster/tenures/?search=${encodeURIComponent(term)}`);
  if (!res.ok) {
    throw new Error('Failed to search tenures');
  }
  return res.json();
}
