/**
 * React Query hooks for the boards system (#3286).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchBoardForOrg, fetchBoardForRoom, fetchBoardPosts } from './api';

export const BOARD_KEYS = {
  forRoom: (roomProfileId: number) => ['boards', 'forRoom', roomProfileId] as const,
  forOrg: (organizationId: number) => ['boards', 'forOrg', organizationId] as const,
  posts: (boardId: number) => ['boards', 'posts', boardId] as const,
};

/** The room's LOCATION board — null when the room carries no Notice Board feature. */
export function useBoardForRoomQuery(roomProfileId?: number | null) {
  return useQuery({
    queryKey: BOARD_KEYS.forRoom(roomProfileId ?? 0),
    queryFn: () => fetchBoardForRoom(roomProfileId as number),
    enabled: roomProfileId != null && roomProfileId > 0,
  });
}

/** The org's board — visible only to active members (server-side gated). */
export function useBoardForOrgQuery(organizationId?: number | null) {
  return useQuery({
    queryKey: BOARD_KEYS.forOrg(organizationId ?? 0),
    queryFn: () => fetchBoardForOrg(organizationId as number),
    enabled: organizationId != null && organizationId > 0,
  });
}

/** Active posts on a board, newest-first (server-side display-capped). */
export function useBoardPostsQuery(boardId?: number | null) {
  return useQuery({
    queryKey: BOARD_KEYS.posts(boardId ?? 0),
    queryFn: () => fetchBoardPosts(boardId as number),
    enabled: boardId != null && boardId > 0,
  });
}
