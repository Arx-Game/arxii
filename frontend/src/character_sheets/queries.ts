/**
 * Character sheet React Query hooks (#1446).
 */

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { fetchProfileTextVersions } from '@/sheet_update_requests/api';
import {
  STAFF_CHOICE_SOURCES,
  fetchCharacterSheet,
  fetchStaffEstateOptions,
  fetchStaffMagicOptions,
  fetchStaffOptions,
  runStaffRowAction,
  type StaffRowAction,
  patchStaffEdit,
  restoreProfileTextVersion,
  type CharacterSheetPayload,
  type StaffChoiceField,
  type StaffEditBody,
} from './api';

export const characterSheetKey = (sheetId: number) => ['character-sheets', sheetId] as const;

/** The rich character-sheet payload for a single character (sheet id == character id). */
export function useCharacterSheetQuery(sheetId: number) {
  return useQuery({
    queryKey: characterSheetKey(sheetId),
    queryFn: () => fetchCharacterSheet(sheetId),
    enabled: !!sheetId,
  });
}

/**
 * A staff edit (#3988). The answer is the refreshed sheet, written straight into the
 * sheet's cache so the page shows the saved value without a second fetch; the prose
 * history is refetched, since a prose save is a new version.
 */
export function useStaffEditMutation(sheetId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StaffEditBody) => patchStaffEdit(sheetId, body),
    onSuccess: (sheet: CharacterSheetPayload) => {
      queryClient.setQueryData(characterSheetKey(sheetId), sheet);
      queryClient.invalidateQueries({ queryKey: profileTextVersionsKey(sheetId) });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'The edit was not saved.'),
  });
}

const profileTextVersionsKey = (sheetId: number) =>
  ['character-sheets', sheetId, 'profile-text-versions'] as const;

/** Every prose version of the sheet (#2631); fetched only while a history is open. */
export function useProfileTextVersions(sheetId: number, enabled: boolean) {
  return useQuery({
    queryKey: profileTextVersionsKey(sheetId),
    queryFn: () => fetchProfileTextVersions(sheetId),
    enabled: enabled && !!sheetId,
  });
}

/** Restore a past version (#3988); it lands as a new version. */
export function useRestoreProfileTextVersion(sheetId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (versionId: number) => restoreProfileTextVersion(sheetId, versionId),
    onSuccess: (sheet: CharacterSheetPayload) => {
      queryClient.setQueryData(characterSheetKey(sheetId), sheet);
      queryClient.invalidateQueries({ queryKey: profileTextVersionsKey(sheetId) });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : 'The version was not restored.'),
  });
}

/** One identity choice's options, fetched the first time its picker opens. */
export function useStaffChoiceOptions(field: StaffChoiceField, enabled: boolean) {
  return useQuery({
    queryKey: ['staff-edit-options', field],
    queryFn: STAFF_CHOICE_SOURCES[field],
    enabled,
    staleTime: 5 * 60_000,
  });
}

/** What the staff row editors pick from (#4221), fetched while edit mode is on. */
export function useStaffOptions(sheetId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['character-sheets', sheetId, 'staff-options'],
    queryFn: () => fetchStaffOptions(sheetId),
    enabled: enabled && !!sheetId,
    staleTime: 5 * 60_000,
  });
}

/** What Grant magic offers (#4224) for the tradition and gift picked so far. */
export function useStaffMagicOptions(
  sheetId: number,
  tradition: string,
  gift: string,
  enabled: boolean
) {
  return useQuery({
    queryKey: ['character-sheets', sheetId, 'staff-magic-options', tradition, gift],
    queryFn: () => fetchStaffMagicOptions(sheetId, tradition, gift),
    enabled: enabled && !!sheetId,
    // The stepper stays drawn while the next pick's options load.
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
}

/** What piece D's editors offer (#4226); ``room`` is the residence search so far. */
export function useStaffEstateOptions(sheetId: number, room: string, enabled: boolean) {
  return useQuery({
    queryKey: ['character-sheets', sheetId, 'staff-estate-options', room],
    queryFn: () => fetchStaffEstateOptions(sheetId, room),
    enabled: enabled && !!sheetId,
    staleTime: 60_000,
    // The editors stay drawn while a new room search loads.
    placeholderData: keepPreviousData,
  });
}

/** One staff row action (#4221); the answer replaces the sheet in the cache. */
export function useStaffRowMutation(sheetId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: StaffRowAction) => runStaffRowAction(sheetId, request),
    onSuccess: (sheet: CharacterSheetPayload) => {
      queryClient.setQueryData(characterSheetKey(sheetId), sheet);
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'The change was not saved.'),
  });
}
