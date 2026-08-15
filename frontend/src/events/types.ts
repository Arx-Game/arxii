export type EventStatus = 'draft' | 'scheduled' | 'active' | 'completed' | 'cancelled';
export type TimePhase = 'dawn' | 'day' | 'dusk' | 'night';

export const EVENT_STATUS = {
  DRAFT: 'draft',
  SCHEDULED: 'scheduled',
  ACTIVE: 'active',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
} as const satisfies Record<string, EventStatus>;

export interface EventListItem {
  id: number;
  name: string;
  description: string;
  location: number;
  location_name: string;
  status: EventStatus;
  is_public: boolean;
  scheduled_real_time: string;
  scheduled_ic_time: string | null;
  time_phase: TimePhase;
  primary_host_name: string | null;
}

export interface EventHost {
  id: number;
  persona: number | null;
  persona_name: string | null;
  is_primary: boolean;
  added_at: string;
}

export type InvitationResponse = 'pending' | 'accepted' | 'declined';

export interface EventInvitation {
  id: number;
  target_type: 'persona' | 'organization' | 'society';
  target_persona: number | null;
  target_organization: number | null;
  target_society: number | null;
  target_name: string | null;
  can_bring_guests: boolean;
  /**
   * The invitee's RSVP (#3069). Only meaningful for `target_type: 'persona'` —
   * organization/society (group) invitations have no per-member response row
   * and always read PENDING server-side (see `InvitationResponse` on the
   * backend, `world/events/constants.py`).
   */
  response: InvitationResponse;
  responded_at: string | null;
  invited_at: string;
}

export interface EventModification {
  room_description_overlay: string;
}

/** What slice of a once-in-a-lifetime event's budget a spend paid for (#2357). */
export type GrandeurCategory = 'venue' | 'entertainment' | 'favors' | 'decor';

export const GRANDEUR_CATEGORIES: { value: GrandeurCategory; label: string }[] = [
  { value: 'venue', label: 'Venue' },
  { value: 'entertainment', label: 'Entertainment' },
  { value: 'favors', label: 'Favors' },
  { value: 'decor', label: 'Decor' },
];

export interface EventGrandeurContribution {
  id: number;
  category: GrandeurCategory;
  contributed_by: number;
  contributed_by_name: string | null;
  amount_spent: number;
  created_at: string;
}

export interface EventDetailData extends EventListItem {
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  hosts: EventHost[];
  invitations: EventInvitation[];
  modification: EventModification | null;
  grandeur_contributions: EventGrandeurContribution[];
  grandeur_total_spent: number;
  is_host: boolean;
  is_gm: boolean;
}

export interface EventCreateData {
  name: string;
  description?: string;
  location: number;
  is_public: boolean;
  scheduled_real_time: string;
  scheduled_ic_time?: string;
  time_phase: TimePhase;
}

export type EventUpdateData = Partial<Omit<EventCreateData, 'location'>>;

export interface PaginatedResponse<T> {
  count: number;
  page_size: number;
  num_pages: number;
  current_page: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AreaListItem {
  id: number;
  name: string;
  level: number;
  level_display: string;
  children_count: number;
}

export interface AreaRoom {
  id: number;
  name: string;
  area_name: string;
}

/** Convert an ISO/UTC datetime string to a `datetime-local` input value in the user's timezone. */
export function toLocalDatetimeValue(isoString: string): string {
  const date = new Date(isoString);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

export const TIME_PHASES: { value: TimePhase; label: string }[] = [
  { value: 'dawn', label: 'Dawn' },
  { value: 'day', label: 'Day' },
  { value: 'dusk', label: 'Dusk' },
  { value: 'night', label: 'Night' },
];

export const EVENT_STATUS_TABS = [
  { value: EVENT_STATUS.SCHEDULED, label: 'Upcoming' },
  { value: EVENT_STATUS.ACTIVE, label: 'Active' },
  { value: EVENT_STATUS.COMPLETED, label: 'Past' },
] as const;
