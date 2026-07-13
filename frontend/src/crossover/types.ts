/** Type aliases for the crossover feature module (#2075). */

import type { components } from '@/generated/api';

export type CrossoverInvite = components['schemas']['CrossoverInvite'];
export type CrossoverInviteStatus = NonNullable<CrossoverInvite['status']>;
export type EpisodeScene = components['schemas']['EpisodeScene'];
export type Beat = components['schemas']['Beat'];

export interface CrossoverInviteCreateBody {
  event: number;
  to_story: number;
  proposed_episode?: number;
  message?: string;
}

export interface CrossoverInviteAcceptBody {
  accepted_episode?: number;
  response_note?: string;
}

export interface ListCrossoverInvitesParams {
  status?: string;
  event?: number;
  to_story?: number;
  from_gm?: number;
  page?: number;
  page_size?: number;
}

export type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
