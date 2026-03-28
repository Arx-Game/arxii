import { apiFetch } from '@/evennia_replacements/api';
import type {
  AreaListItem,
  AreaRoom,
  EventCreateData,
  EventDetailData,
  EventListItem,
  PaginatedResponse,
} from './types';

export async function fetchEvents(
  params: Record<string, string>
): Promise<PaginatedResponse<EventListItem>> {
  const query = new URLSearchParams(params).toString();
  const res = await apiFetch(`/api/events/?${query}`);
  if (!res.ok) throw new Error('Failed to load events');
  return res.json();
}

export async function fetchEvent(id: string): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/`);
  if (!res.ok) throw new Error('Failed to load event');
  return res.json();
}

export async function createEvent(data: EventCreateData): Promise<EventDetailData> {
  const res = await apiFetch('/api/events/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || err.non_field_errors?.[0] || 'Failed to create event');
  }
  return res.json();
}

export async function updateEvent(
  id: string,
  data: Partial<EventCreateData>
): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update event');
  return res.json();
}

export async function eventLifecycleAction(
  id: number,
  action: 'schedule' | 'start' | 'complete' | 'cancel'
): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/${action}/`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to ${action} event`);
  }
  return res.json();
}

export async function fetchAreas(parentId?: number): Promise<AreaListItem[]> {
  const params = parentId != null ? `?parent=${parentId}` : '?has_parent=false';
  const res = await apiFetch(`/api/areas/${params}`);
  if (!res.ok) throw new Error('Failed to load areas');
  return res.json();
}

export async function fetchAreaRooms(areaId: number): Promise<AreaRoom[]> {
  const res = await apiFetch(`/api/areas/${areaId}/rooms/`);
  if (!res.ok) throw new Error('Failed to load rooms');
  return res.json();
}
