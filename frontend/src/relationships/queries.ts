/**
 * React Query hooks for the relationships module (#2031, #2159).
 *
 * Covers the writeups-commend surface, the track catalog, the caller's own
 * relationship-to-target lookup, and the four relationship-building write
 * actions backing `RelationshipWriteupDialog`. Follows the same key-factory +
 * hook shape as frontend/src/magic/queries.ts.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type {
  CapstoneWriteRequest,
  DevelopmentWriteRequest,
  FirstImpressionWriteRequest,
  GiveWriteupKudosRequest,
  RedistributeWriteRequest,
  RelationshipTimelineParams,
  RelationshipWriteResult,
  WriteupComplaintWriteRequest,
} from './api';

export const relationshipsKeys = {
  all: ['relationships'] as const,
  /**
   * `writeups()` (no arg) is the shared prefix used to invalidate every
   * subject-scoped variant at once; `writeups(subjectCharacterId)` is the
   * specific key a given sheet's query is cached under.
   */
  writeups: (subjectCharacterId?: number) =>
    subjectCharacterId == null
      ? ([...relationshipsKeys.all, 'writeups'] as const)
      : ([...relationshipsKeys.all, 'writeups', subjectCharacterId] as const),
  tracks: () => [...relationshipsKeys.all, 'tracks'] as const,
  /** Same no-arg/scoped-arg shape as `writeups` — see there. */
  myRelationship: (targetCharacterSheetId?: number) =>
    targetCharacterSheetId == null
      ? ([...relationshipsKeys.all, 'my-relationship'] as const)
      : ([...relationshipsKeys.all, 'my-relationship', targetCharacterSheetId] as const),
  /** The caller's full outbound relationship list from one owned character (`?source=`). */
  outbound: (sourceCharacterSheetId?: number) =>
    sourceCharacterSheetId == null
      ? ([...relationshipsKeys.all, 'outbound'] as const)
      : ([...relationshipsKeys.all, 'outbound', sourceCharacterSheetId] as const),
  /** One relationship's full detail (incl. `track_progress`) — `RelationshipPanel` row expand. */
  detail: (relationshipId: number) => [...relationshipsKeys.all, 'detail', relationshipId] as const,
  /** Merged Update/Development/Capstone timeline — either arm, keyed by whichever param is set. */
  timeline: (params: RelationshipTimelineParams) =>
    [
      ...relationshipsKeys.all,
      'timeline',
      params.relationship ?? null,
      params.aboutCharacter ?? null,
    ] as const,
};

/**
 * GET the caller's commendable writeups about one owned character
 * (tenure-scoped, SHARED/PUBLIC only).
 *
 * `subjectCharacterId` (the viewed CharacterSheet pk) is threaded into both
 * the request (`?subject_character=`) and the query key — required because
 * the endpoint is scoped to the requester's *account*, which may tenure-own
 * more than one character; without narrowing, a multi-character account's
 * Writeups subsection would show every owned character's writeups under
 * whichever sheet happens to be open (fix wave, Finding 2).
 *
 * Pass `enabled=false` when viewing a character sheet that is NOT the
 * caller's own — fetching it on a foreign sheet would return the *viewer's*
 * own writeups, not the viewed character's.
 */
export function useMyWriteups(subjectCharacterId?: number, enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.writeups(subjectCharacterId),
    queryFn: () => api.getMyWriteups(subjectCharacterId),
    enabled,
  });
}

/**
 * Commend a relationship writeup. Invalidates the writeups list so
 * kudos_count/viewer_has_kudosed refresh on success.
 */
export function useGiveWriteupKudos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GiveWriteupKudosRequest) => api.giveWriteupKudos(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: relationshipsKeys.writeups() }).catch(() => {});
    },
  });
}

/** GET the full relationship-track catalog (with nested tiers), unpaginated. */
export function useRelationshipTracks() {
  return useQuery({
    queryKey: relationshipsKeys.tracks(),
    queryFn: api.getRelationshipTracks,
  });
}

/**
 * GET the caller's own outbound relationship(s) toward one target character
 * (CharacterSheet pk). Feeds `RelationshipWriteupDialog`'s impression-vs-development
 * mode branching in the card drawer's "Record an impression" quick action.
 */
export function useMyRelationshipToTarget(targetCharacterSheetId?: number, enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.myRelationship(targetCharacterSheetId),
    queryFn: () => api.getMyRelationshipToTarget(targetCharacterSheetId as number),
    enabled: enabled && targetCharacterSheetId != null,
  });
}

/**
 * GET the caller's full outbound relationship list from one owned character
 * (CharacterSheet pk). Feeds `RelationshipPanel`'s own-sheet arm — the
 * lightweight list serializer (no `track_progress`; see `useRelationshipDetail`
 * for that on row expand).
 */
export function useMyOutboundRelationships(sourceCharacterSheetId?: number, enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.outbound(sourceCharacterSheetId),
    queryFn: () => api.getMyOutboundRelationships(sourceCharacterSheetId as number),
    enabled: enabled && sourceCharacterSheetId != null,
  });
}

/**
 * GET one relationship's full detail, including per-track `track_progress`
 * (points/tier). Used to expand one row in `RelationshipPanel`'s own-sheet
 * arm — pass `enabled=false` until the row is actually expanded so this
 * doesn't fire for every row up front.
 */
export function useRelationshipDetail(relationshipId: number | null, enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.detail(relationshipId ?? 0),
    queryFn: () => api.getRelationshipDetail(relationshipId as number),
    enabled: enabled && relationshipId != null,
  });
}

/**
 * GET the merged Update/Development/Capstone writeup timeline. Exactly one
 * of `relationship`/`aboutCharacter` should be set (mirrors the backend's
 * mutually-exclusive 400) — this hook only fires once one of them is.
 */
export function useRelationshipTimeline(params: RelationshipTimelineParams, enabled = true) {
  return useQuery({
    queryKey: relationshipsKeys.timeline(params),
    queryFn: () => api.getRelationshipTimeline(params),
    enabled: enabled && (params.relationship != null || params.aboutCharacter != null),
  });
}

/**
 * File a bad-faith-RP complaint against a writeup. No cache invalidation —
 * `WriteupComplaint` never appears in any player-facing serializer, so there
 * is nothing this mutation's success would change the shape of.
 */
export function useFileWriteupComplaint() {
  return useMutation({
    mutationFn: (body: WriteupComplaintWriteRequest) => api.fileWriteupComplaint(body),
  });
}

/**
 * Shared mutation shape for the four relationship-building write actions
 * (first_impression/develop/capstone/redistribute): all invalidate the same
 * relationship query prefix on success (writeups, track catalog, and any
 * cached my-relationship-to-target lookups all potentially change).
 */
function useRelationshipWriteMutation<TBody>(
  mutationFn: (body: TBody) => Promise<RelationshipWriteResult>
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: relationshipsKeys.all }).catch(() => {});
    },
  });
}

/** Record a first impression (unilateral, creates a pending relationship). */
export function useCreateFirstImpression() {
  return useRelationshipWriteMutation((body: FirstImpressionWriteRequest) =>
    api.postFirstImpression(body)
  );
}

/** Solidify temporary points into permanent developed points (7/week cap, server-enforced). */
export function useCreateDevelopment() {
  return useRelationshipWriteMutation((body: DevelopmentWriteRequest) => api.postDevelopment(body));
}

/** Record a monumental relationship capstone (never gated). */
export function useCreateCapstone() {
  return useRelationshipWriteMutation((body: CapstoneWriteRequest) => api.postCapstone(body));
}

/** Redistribute developed points between tracks in an existing relationship. */
export function useRedistributePoints() {
  return useRelationshipWriteMutation((body: RedistributeWriteRequest) =>
    api.postRedistribute(body)
  );
}
