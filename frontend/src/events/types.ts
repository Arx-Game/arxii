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
