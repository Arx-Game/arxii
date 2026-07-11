import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  fetchRosterEntry,
  fetchMyRosterEntries,
  fetchMyTenures,
  fetchRosters,
  fetchRosterEntries,
  postRosterApplication,
  fetchPlayerMedia,
  uploadPlayerMedia,
  associateMedia,
  fetchTenureGalleries,
  createTenureGallery,
  updateTenureGallery,
} from './api';
import type {
  RosterEntryData,
  RosterData,
  CharacterData,
  PlayerMedia,
  TenureGallery,
} from './types';
import type { PaginatedResponse } from '@/shared/types';
import { useAccount } from '@/store/hooks';

export function useRosterEntryQuery(id: RosterEntryData['id']) {
  return useQuery({
    queryKey: ['roster-entry', id],
    queryFn: () => fetchRosterEntry(id),
    enabled: !!id,
    throwOnError: true,
  });
}

export function useMyRosterEntriesQuery(enabled = true) {
  const account = useAccount();
  return useQuery({
    queryKey: ['my-roster-entries'],
    queryFn: fetchMyRosterEntries,
    enabled: !!account && enabled,
    throwOnError: true,
  });
}

export function useMyTenuresQuery(enabled = true) {
  const account = useAccount();
  return useQuery({
    queryKey: ['my-tenures'],
    queryFn: fetchMyTenures,
    enabled: !!account && enabled,
    throwOnError: true,
  });
}

export function useRostersQuery() {
  return useQuery({
    queryKey: ['rosters'],
    queryFn: fetchRosters,
    throwOnError: true,
  });
}

export function useRosterEntriesQuery(
  rosterId: RosterData['id'] | undefined,
  page: number,
  filters: Partial<Pick<CharacterData, 'name' | 'char_class' | 'gender'>>
) {
  return useQuery<PaginatedResponse<RosterEntryData>>({
    queryKey: ['roster-entries', rosterId, page, filters],
    queryFn: () => fetchRosterEntries(rosterId!, page, filters),
    enabled: !!rosterId,
    throwOnError: true,
  });
}

/**
 * Public roster search by exact persona name (#2156) — the character-card drawer's
 * ONLY allowed identity-resolution path. Searches across every public roster (no
 * `roster` scope) since a persona name isn't tied to one; the `name` filter is
 * `icontains` server-side, so callers must still check for an exact
 * `result.character.name === name` match before treating it as a hit — a
 * disguised/temporary persona whose name doesn't exactly match a public roster
 * entry must render as "not on the roster," never fall back to a substring match.
 */
export function useRosterEntryByNameQuery(name: string | undefined) {
  return useQuery<PaginatedResponse<RosterEntryData>>({
    queryKey: ['roster-entry-by-name', name],
    queryFn: () => fetchRosterEntries(undefined, 1, { name }),
    enabled: !!name,
    throwOnError: true,
  });
}

export function useSendRosterApplication(id: RosterEntryData['id']) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (message: string) => postRosterApplication(id, message),
    onSuccess: () => {
      toast.success('Application sent! Staff will review it — you will get an email.');
      queryClient.invalidateQueries({ queryKey: ['roster-entry', id] });
      // ['account'] is the query key useAccountQuery() (mounted globally via
      // AuthProvider) reads and mirrors into Redux — invalidating it here
      // refetches /api/user/ so the new pending_applications entry shows up
      // without a full page reload.
      queryClient.invalidateQueries({ queryKey: ['account'] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Failed to send.'),
  });
}

export function usePlayerMediaQuery(enabled = true) {
  return useQuery({
    queryKey: ['player-media'],
    queryFn: fetchPlayerMedia,
    enabled,
    throwOnError: true,
  });
}

export function useUploadPlayerMedia() {
  return useMutation({
    mutationFn: uploadPlayerMedia,
  });
}

export function useAssociateMedia() {
  return useMutation({
    mutationFn: ({
      mediaId,
      tenureId,
      galleryId,
    }: {
      mediaId: PlayerMedia['id'];
      tenureId: number;
      galleryId?: number;
    }) => associateMedia(mediaId, tenureId, galleryId),
  });
}

export function useTenureGalleriesQuery(tenureId: number | undefined) {
  return useQuery<TenureGallery[]>({
    queryKey: ['tenure-galleries', tenureId],
    queryFn: () => fetchTenureGalleries(tenureId!),
    enabled: !!tenureId,
    throwOnError: true,
  });
}

export function useUpdateGallery() {
  return useMutation({
    mutationFn: ({ galleryId, data }: { galleryId: number; data: Partial<TenureGallery> }) =>
      updateTenureGallery(galleryId, data),
  });
}

export function useCreateGallery() {
  return useMutation({
    mutationFn: ({
      tenureId,
      data,
    }: {
      tenureId: number;
      data: Pick<TenureGallery, 'name' | 'is_public' | 'allowed_viewers'>;
    }) => createTenureGallery(tenureId, data),
  });
}
