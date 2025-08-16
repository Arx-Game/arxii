import type {
  RosterEntryData,
  MyRosterEntry,
  RosterData,
  CharacterData,
  PlayerMedia,
  TenureGallery,
} from './types';
import type { PaginatedResponse } from '@/shared/types';
import { apiFetch } from '../evennia_replacements/api';

export async function fetchRosterEntry(id: RosterEntryData['id']): Promise<RosterEntryData> {
  const res = await apiFetch(`/api/roster/entries/${id}/`);
  if (!res.ok) {
    throw new Error('Failed to load roster entry');
  }
  return res.json();
}

export async function fetchMyRosterEntries(): Promise<MyRosterEntry[]> {
  const res = await apiFetch('/api/roster/entries/mine/');
  if (!res.ok) {
    throw new Error('Failed to load characters');
  }
  return res.json();
}

export async function fetchMyTenures(): Promise<{ id: number; display_name: string }[]> {
  const res = await apiFetch('/api/roster/tenures/mine/');
  if (!res.ok) {
    throw new Error('Failed to load tenures');
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

export async function fetchPlayerMedia(): Promise<PlayerMedia[]> {
  const res = await apiFetch('/api/roster/media/');
  if (!res.ok) {
    throw new Error('Failed to load media');
  }
  return res.json();
}

export async function uploadPlayerMedia(form: FormData): Promise<PlayerMedia> {
  const res = await apiFetch('/api/roster/media/', { method: 'POST', body: form });
  if (!res.ok) {
    throw new Error('Failed to upload media');
  }
  return res.json();
}

export async function associateMedia(
  mediaId: PlayerMedia['id'],
  tenureId: number,
  galleryId?: number
): Promise<void> {
  const res = await apiFetch(`/api/roster/media/${mediaId}/associate_tenure/`, {
    method: 'POST',
    body: JSON.stringify({ tenure_id: tenureId, gallery_id: galleryId }),
  });
  if (!res.ok) {
    throw new Error('Failed to associate media');
  }
}

export async function fetchTenureGalleries(tenureId: number): Promise<TenureGallery[]> {
  const res = await apiFetch(`/api/roster/galleries/?tenure=${tenureId}`);
  if (!res.ok) {
    throw new Error('Failed to load galleries');
  }
  return res.json();
}

export async function createTenureGallery(
  tenureId: number,
  data: Pick<TenureGallery, 'name' | 'is_public' | 'allowed_viewers'>
): Promise<TenureGallery> {
  const res = await apiFetch(`/api/roster/galleries/`, {
    method: 'POST',
    body: JSON.stringify({ ...data, tenure_id: tenureId }),
  });
  if (!res.ok) {
    throw new Error('Failed to create gallery');
  }
  return res.json();
}

export async function updateTenureGallery(
  galleryId: TenureGallery['id'],
  data: Partial<Pick<TenureGallery, 'is_public' | 'allowed_viewers' | 'name'>>
): Promise<TenureGallery> {
  const res = await apiFetch(`/api/roster/galleries/${galleryId}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to update gallery');
  }
  return res.json();
}

export async function fetchRosterEntries(
  rosterId: RosterData['id'],
  page = 1,
  filters: Partial<Pick<CharacterData, 'name' | 'char_class' | 'gender'>> = {}
): Promise<PaginatedResponse<RosterEntryData>> {
  const params = new URLSearchParams({ roster: String(rosterId), page: String(page) });
  if (filters.name) params.set('name', filters.name);
  if (filters.char_class) params.set('char_class', filters.char_class);
  if (filters.gender) params.set('gender', filters.gender);
  const res = await apiFetch(`/api/roster/entries/?${params.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to load roster entries');
  }
  return res.json();
}
export async function postRosterApplication(
  id: RosterEntryData['id'],
  message: string
): Promise<void> {
  const res = await apiFetch(`/api/roster/entries/${id}/apply/`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    throw new Error(`Failed to send application for character ${id}`);
  }
}
