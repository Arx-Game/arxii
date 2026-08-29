import { apiFetch } from '@/evennia_replacements/api';
import type {
  AreaListItem,
  AreaRoom,
  EventCreateData,
  EventDetailData,
  EventInvitation,
  EventListItem,
  EventUpdateData,
  GrandeurCategory,
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
  targetId: number,
  invitedByPersona?: number
): Promise<EventInvitation> {
  const res = await apiFetch('/api/events/invitations/', {
    method: 'POST',
    body: JSON.stringify({
      event: eventId,
      target_type: targetType,
      target_id: targetId,
      invited_by_persona: invitedByPersona,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to send invitation');
  }
  return res.json();
}

/**
 * Every `EventInvitation` visible to the caller (#3412 — Hall Attention band).
 * `EventInvitationViewSet.list` already scopes server-side to invitations
 * targeting the caller's own personas or events they host (`_apply_list_visibility`,
 * `world/events/views.py`) — no `response`/pending filter exists on
 * `EventInvitationFilter` (verified #3412 T1), so callers filter to pending +
 * "mine" client-side, mirroring `EventInvitations.tsx`'s own persona-matching.
 */
export async function fetchMyEventInvitations(): Promise<PaginatedResponse<EventInvitation>> {
  const res = await apiFetch('/api/events/invitations/');
  if (!res.ok) throw new Error('Failed to load invitations');
  return res.json();
}

export async function removeInvitation(invitationId: number): Promise<void> {
  const res = await apiFetch(`/api/events/invitations/${invitationId}/`, {
    method: 'DELETE',
  });
  if (res.status !== 204) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to remove invitation');
  }
}

/**
 * #3069 — the invitee's own RSVP (accept/decline) on `/respond/`.
 *
 * The endpoint's real response is `{success, message}` (see
 * `EventInvitationViewSet.respond`, `world/events/views.py`) — NOT the
 * `EventInvitation` shape the generated OpenAPI types claim (a pre-existing
 * `@extend_schema` gap on that action, out of scope for this fix).
 */
export async function respondToInvitation(
  invitationId: number,
  response: 'accept' | 'decline'
): Promise<{ success: boolean; message: string }> {
  const res = await apiFetch(`/api/events/invitations/${invitationId}/respond/`, {
    method: 'POST',
    body: JSON.stringify({ response }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to send your RSVP');
  }
  return data;
}

/**
 * Invest in an event's grandeur budget (#2357) — dispatches
 * ``ContributeGrandeurAction`` through the generic action-dispatch endpoint
 * (same seam as the covenant treasury calls, ``covenants/api.ts``).
 * ``organizationId`` sources the spend from that organization's treasury
 * (spend-authority checked server-side); omit it to spend from the actor's
 * own purse. ``DispatchActionView`` returns HTTP 200 even for a business-rule
 * rejection, so ``success`` (not ``res.ok`` alone) is the real signal.
 */
export async function contributeGrandeur(
  actorCharacterId: number,
  eventId: number,
  category: GrandeurCategory,
  amount: number,
  organizationId?: number
): Promise<string> {
  const res = await apiFetch(`/api/actions/characters/${actorCharacterId}/dispatch/`, {
    method: 'POST',
    body: JSON.stringify({
      ref: { backend: 'registry', registry_key: 'event_invest_grandeur' },
      kwargs: {
        event_id: eventId,
        category,
        amount,
        organization_id: organizationId ?? null,
      },
    }),
  });
  const data = (await res.json().catch(() => ({}))) as {
    detail?: string;
    message?: string | null;
    success?: boolean | null;
  };
  const message = data.detail ?? data.message ?? undefined;
  if (!res.ok || data.success === false) {
    throw new Error(message ?? 'Failed to invest in grandeur.');
  }
  return message ?? 'Investment recorded.';
}

export interface PersonaSearchResult {
  /** Persona pk. */
  id: number;
  name: string;
  /** Owning CharacterSheet pk — some callers key on the sheet, not the persona (#audit2). */
  character_sheet: number | null;
}

export async function searchPersonas(query: string): Promise<PersonaSearchResult[]> {
  const res = await apiFetch(`/api/personas/?search=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search personas');
  const data = await res.json();
  const results = Array.isArray(data) ? data : data.results;
  return results.map((p: { id: number; name: string; character_sheet: number | null }) => ({
    id: p.id,
    name: p.name,
    character_sheet: p.character_sheet ?? null,
  }));
}

export async function searchOrganizations(query: string): Promise<{ id: number; name: string }[]> {
  const res = await apiFetch(`/api/events/organizations/?search=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search organizations');
  const data = await res.json();
  const results = Array.isArray(data) ? data : data.results;
  return results.map((o: { id: number; name: string }) => ({ id: o.id, name: o.name }));
}

export async function searchSocieties(query: string): Promise<{ id: number; name: string }[]> {
  const res = await apiFetch(`/api/events/societies/?search=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search societies');
  const data = await res.json();
  const results = Array.isArray(data) ? data : data.results;
  return results.map((s: { id: number; name: string }) => ({ id: s.id, name: s.name }));
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
