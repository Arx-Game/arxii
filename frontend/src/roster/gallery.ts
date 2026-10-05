/**
 * A character's Gallery (#4151): its pictures, looks, storage, and the changes its
 * player makes. The rules (what can be a look, what may be worn, who may delete) live
 * server-side in `world.roster.services.gallery`; these calls only carry the request.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { components } from '@/generated/api';
import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import { fetchAllPages } from '@/lib/pagination';

export type GalleryPicture = components['schemas']['GalleryPicture'];
export type MoodOption = components['schemas']['MoodOption'];
export type MediaUsage = components['schemas']['MediaUsage'];
export type Crop = components['schemas']['Crop'];

/** What the owner changes on one picture. `crop: null` makes a look a plain picture. */
export interface PictureChange {
  title?: string;
  caption?: string;
  is_nsfw?: boolean;
  mood?: number | null;
  crop?: Crop | null;
  /** With a crop: also make this the worn look. */
  wear?: boolean;
}

export type DeleteOutcome = 'deleted' | 'unlinked';

const BASE = '/api/roster/tenure-media/';

export function fetchGallery(entryId: number): Promise<GalleryPicture[]> {
  return fetchAllPages<GalleryPicture>(
    `${BASE}?roster_entry=${entryId}`,
    'Failed to load the gallery.'
  );
}

export async function uploadPictures(entryId: number, files: File[]): Promise<GalleryPicture[]> {
  const form = new FormData();
  form.append('roster_entry', String(entryId));
  files.forEach((file) => form.append('images', file));
  const res = await apiFetch(BASE, { method: 'POST', body: form });
  if (!res.ok) {
    await readErrorDetail(res, 'Those pictures could not be added.');
  }
  return res.json();
}

export async function changePicture(id: number, change: PictureChange): Promise<GalleryPicture> {
  const res = await apiFetch(`${BASE}${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(change),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'That change could not be saved.');
  }
  return res.json();
}

export async function deletePicture(id: number): Promise<DeleteOutcome> {
  const res = await apiFetch(`${BASE}${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    await readErrorDetail(res, 'That picture could not be deleted.');
  }
  const body: { outcome: DeleteOutcome } = await res.json();
  return body.outcome;
}

export async function reorderGallery(entryId: number, ids: number[]): Promise<void> {
  const res = await apiFetch(`${BASE}reorder/`, {
    method: 'POST',
    body: JSON.stringify({ roster_entry: entryId, ids }),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'The new order could not be saved.');
  }
}

export async function setPictureHidden(id: number, hidden: boolean): Promise<GalleryPicture> {
  const res = await apiFetch(`${BASE}${id}/${hidden ? 'hide' : 'show'}/`, { method: 'POST' });
  if (!res.ok) {
    await readErrorDetail(res, 'That could not be changed.');
  }
  return res.json();
}

export async function fetchMediaUsage(): Promise<MediaUsage> {
  const res = await apiFetch(`${BASE}usage/`);
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to load storage.');
  }
  return res.json();
}

export function fetchMoodOptions(): Promise<MoodOption[]> {
  return fetchAllPages<MoodOption>('/api/character-sheets/mood-options/', 'Failed to load moods.');
}

// ---------------------------------------------------------------- hooks

export const galleryKey = (entryId: number) => ['gallery', entryId] as const;

export function useGalleryQuery(entryId: number, enabled = true) {
  return useQuery({
    queryKey: galleryKey(entryId),
    queryFn: () => fetchGallery(entryId),
    enabled: enabled && entryId > 0,
  });
}

export function useMediaUsageQuery(enabled: boolean) {
  return useQuery({ queryKey: ['media-usage'], queryFn: fetchMediaUsage, enabled });
}

export function useMoodOptionsQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['mood-options'],
    queryFn: fetchMoodOptions,
    enabled,
    staleTime: Infinity,
  });
}

/**
 * Every gallery change can move the worn look, so each one refreshes the gallery, the
 * sheet (plate and looks strip), the roster entry and the player's own entries (the
 * portrait chips), plus storage when a file came or went.
 */
function useGalleryInvalidation(entryId: number, sheetId: number) {
  const queryClient = useQueryClient();
  return (storageChanged = false) => {
    queryClient.invalidateQueries({ queryKey: galleryKey(entryId) });
    queryClient.invalidateQueries({ queryKey: ['character-sheets', sheetId] });
    queryClient.invalidateQueries({ queryKey: ['roster-entry', entryId] });
    queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
    if (storageChanged) queryClient.invalidateQueries({ queryKey: ['media-usage'] });
  };
}

const showError = (err: unknown, fallback: string) =>
  toast.error(err instanceof Error ? err.message : fallback);

export function useUploadPictures(entryId: number, sheetId: number) {
  const refresh = useGalleryInvalidation(entryId, sheetId);
  return useMutation({
    mutationFn: (files: File[]) => uploadPictures(entryId, files),
    onSuccess: () => refresh(true),
    onError: (err) => showError(err, 'Those pictures could not be added.'),
  });
}

export function useChangePicture(entryId: number, sheetId: number) {
  const refresh = useGalleryInvalidation(entryId, sheetId);
  return useMutation({
    mutationFn: ({ id, change }: { id: number; change: PictureChange }) =>
      changePicture(id, change),
    onSuccess: () => refresh(),
    onError: (err) => showError(err, 'That change could not be saved.'),
  });
}

export function useDeletePicture(entryId: number, sheetId: number) {
  const refresh = useGalleryInvalidation(entryId, sheetId);
  return useMutation({
    mutationFn: (id: number) => deletePicture(id),
    onSuccess: () => refresh(true),
    onError: (err) => showError(err, 'That picture could not be deleted.'),
  });
}

export function useReorderGallery(entryId: number, sheetId: number) {
  const refresh = useGalleryInvalidation(entryId, sheetId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) => reorderGallery(entryId, ids),
    // Show the new order at once; the refresh confirms it, or puts it back on failure.
    onMutate: (ids) => {
      const before = queryClient.getQueryData<GalleryPicture[]>(galleryKey(entryId));
      if (before) {
        const byId = new Map(before.map((p) => [p.id, p]));
        queryClient.setQueryData(
          galleryKey(entryId),
          ids.map((id) => byId.get(id)).filter((p): p is GalleryPicture => p !== undefined)
        );
      }
    },
    onSettled: () => refresh(),
    onError: (err) => showError(err, 'The new order could not be saved.'),
  });
}

export function useSetPictureHidden(entryId: number, sheetId: number) {
  const refresh = useGalleryInvalidation(entryId, sheetId);
  return useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) => setPictureHidden(id, hidden),
    onSuccess: () => refresh(),
    onError: (err) => showError(err, 'That could not be changed.'),
  });
}
