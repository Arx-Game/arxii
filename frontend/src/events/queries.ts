import { apiFetch } from '@/evennia_replacements/api';
import type {
  AreaListItem,
  AreaRoom,
  EventCreateData,
  EventDetailData,
  EventListItem,
  EventUpdateData,
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

export async function updateEvent(id: string, data: EventUpdateData): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || err.non_field_errors?.[0] || 'Failed to update event');
  }
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

export async function inviteToEvent(
  eventId: number,
  targetType: 'persona' | 'organization' | 'society',
  targetId: number
): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${eventId}/invite/`, {
    method: 'POST',
    body: JSON.stringify({ target_type: targetType, target_id: targetId }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to send invitation');
  }
  return res.json();
}

export async function removeInvitation(
  eventId: number,
  invitationId: number
): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${eventId}/remove-invitation/`, {
    method: 'POST',
    body: JSON.stringify({ invitation_id: invitationId }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to remove invitation');
  }
  return res.json();
}

export async function searchPersonas(query: string): Promise<{ id: number; name: string }[]> {
  const res = await apiFetch(`/api/personas/?search=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search personas');
  const data = await res.json();
  const results = Array.isArray(data) ? data : data.results;
  return results.map((p: { id: number; name: string }) => ({ id: p.id, name: p.name }));
}

export async function searchOrganizations(query: string): Promise<{ id: number; name: string }[]> {
  const res = await apiFetch(
    `/api/events/search-organizations/?search=${encodeURIComponent(query)}`
  );
  if (!res.ok) throw new Error('Failed to search organizations');
  return res.json();
}

export async function searchSocieties(query: string): Promise<{ id: number; name: string }[]> {
  const res = await apiFetch(`/api/events/search-societies/?search=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search societies');
  return res.json();
}

export async function fetchAreas(parentId?: number): Promise<AreaListItem[]> {
  const params = parentId != null ? `?parent=${parentId}` : '?has_parent=false';
  const res = await apiFetch(`/api/areas/${params}`);
  if (!res.ok) throw new Error('Failed to load areas');
  const data = await res.json();
  // Handle paginated response from AreaViewSet
  return Array.isArray(data) ? data : data.results;
}

export async function fetchAreaRooms(areaId: number): Promise<AreaRoom[]> {
  const res = await apiFetch(`/api/areas/rooms/?area=${areaId}`);
  if (!res.ok) throw new Error('Failed to load rooms');
  const data = await res.json();
  return Array.isArray(data) ? data : data.results;
}
