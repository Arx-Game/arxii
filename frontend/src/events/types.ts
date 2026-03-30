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

export interface EventInvitation {
  id: number;
  target_type: 'persona' | 'organization' | 'society';
  target_persona: number | null;
  target_organization: number | null;
  target_society: number | null;
  target_name: string | null;
  can_bring_guests: boolean;
  invited_at: string;
}

export interface EventModification {
  room_description_overlay: string;
}

export interface EventDetailData extends EventListItem {
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  hosts: EventHost[];
  invitations: EventInvitation[];
  modification: EventModification | null;
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
