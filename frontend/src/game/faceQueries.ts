/**
 * A face's own description and portrait (#4033, #4889): the writes behind the guise sheet's
 * "How this face looks" section and its picture picker. A face is a persona or an alternate
 * self; the portrait goes to whichever the dialog was opened on.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import { fetchAllPages } from '@/lib/pagination';

import { alternateSelfKeys } from './formQueries';
import { personaKeys } from './personaQueries';

/** One of the player's own pictures in the portrait picker. */
export interface PortraitChoice {
  id: number;
  url: string;
  title: string;
  file_size_bytes: number | null;
}

/** The face a portrait change is for. */
export type FaceTarget =
  { kind: 'persona'; personaId: number } | { kind: 'alternate'; alternateSelfId: number };

/** What the player did to the portrait: pick a picture, upload a file, or remove it. */
export type PortraitChange =
  { kind: 'pick'; mediaId: number } | { kind: 'upload'; file: File } | { kind: 'clear' };

function portraitRequest(target: FaceTarget, change: PortraitChange): [string, RequestInit] {
  const url =
    target.kind === 'persona'
      ? '/api/personas/set-portrait/'
      : `/api/forms/alternate-selves/${target.alternateSelfId}/set-portrait/`;
  const personaId = target.kind === 'persona' ? { persona_id: target.personaId } : {};
  if (change.kind === 'upload') {
    const form = new FormData();
    if (target.kind === 'persona') form.append('persona_id', String(target.personaId));
    form.append('image_file', change.file);
    return [url, { method: 'POST', body: form }];
  }
  const body = change.kind === 'pick' ? { media_id: change.mediaId } : { clear: true };
  return [url, { method: 'POST', body: JSON.stringify({ ...personaId, ...body }) }];
}

async function setPortrait(target: FaceTarget, change: PortraitChange): Promise<void> {
  const [url, init] = portraitRequest(target, change);
  const res = await apiFetch(url, init);
  if (!res.ok) {
    await readErrorDetail(res, 'The portrait could not be saved.');
  }
}

/** Refresh every surface that shows a face once its picture or description changed. */
function useFaceInvalidation(characterSheetId: number | null) {
  const qc = useQueryClient();
  return (storageChanged: boolean) => {
    if (characterSheetId !== null) {
      qc.invalidateQueries({ queryKey: personaKeys.forCharacterSheet(characterSheetId) });
      qc.invalidateQueries({ queryKey: alternateSelfKeys.forCharacterSheet(characterSheetId) });
      qc.invalidateQueries({ queryKey: ['character-sheets', characterSheetId] });
    }
    qc.invalidateQueries({ queryKey: ['my-roster-entries'] });
    if (storageChanged) {
      qc.invalidateQueries({ queryKey: ['media-usage'] });
      qc.invalidateQueries({ queryKey: ['portrait-choices'] });
    }
  };
}

/** Pick, upload or remove a face's portrait; the refusal's own words reach the caller. */
export function useFacePortraitMutation(characterSheetId: number | null) {
  const refresh = useFaceInvalidation(characterSheetId);
  return useMutation({
    mutationFn: ({ target, change }: { target: FaceTarget; change: PortraitChange }) =>
      setPortrait(target, change),
    onSuccess: () => refresh(true),
  });
}

async function setDescription(personaId: number, description: string): Promise<void> {
  const res = await apiFetch('/api/personas/set-description/', {
    method: 'POST',
    body: JSON.stringify({ persona_id: personaId, description }),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'The description could not be saved.');
  }
}

/** Write a mask's own description; blank clears it. */
export function useSetFaceDescriptionMutation(characterSheetId: number | null) {
  const refresh = useFaceInvalidation(characterSheetId);
  return useMutation({
    mutationFn: ({ personaId, description }: { personaId: number; description: string }) =>
      setDescription(personaId, description),
    onSuccess: () => refresh(false),
  });
}

/** The player's own pictures a portrait may be picked from. */
export function usePortraitChoicesQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['portrait-choices'],
    queryFn: () =>
      fetchAllPages<PortraitChoice>('/api/personas/portrait-choices/', 'Failed to load pictures.'),
    enabled,
  });
}
