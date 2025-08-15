import { useQuery, useMutation } from '@tanstack/react-query';
import {
  fetchRosterEntry,
  fetchMyRosterEntries,
  fetchRosters,
  fetchRosterEntries,
  postRosterApplication,
  fetchPlayerMedia,
  uploadPlayerMedia,
  associateMedia,
  fetchTenureGalleries,
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

export function useSendRosterApplication(id: RosterEntryData['id']) {
  return useMutation({
    mutationFn: (message: string) => postRosterApplication(id, message),
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
