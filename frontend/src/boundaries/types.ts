import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Generated schema aliases (#1771)
// ---------------------------------------------------------------------------

export type ContentTheme = components['schemas']['ContentTheme'];
export type PaginatedContentThemeList = components['schemas']['PaginatedContentThemeList'];

export type PlayerBoundary = components['schemas']['PlayerBoundary'];
export type PlayerBoundaryRequest = components['schemas']['PlayerBoundaryRequest'];
export type PatchedPlayerBoundaryRequest = components['schemas']['PatchedPlayerBoundaryRequest'];
export type PlayerBoundaryKindEnum = components['schemas']['PlayerBoundaryKindEnum'];
export type PaginatedPlayerBoundaryList = components['schemas']['PaginatedPlayerBoundaryList'];

export type TreasuredSubject = components['schemas']['TreasuredSubject'];
export type TreasuredSubjectRequest = components['schemas']['TreasuredSubjectRequest'];
export type PatchedTreasuredSubjectRequest =
  components['schemas']['PatchedTreasuredSubjectRequest'];
export type SubjectKindEnum = components['schemas']['SubjectKindEnum'];
export type PaginatedTreasuredSubjectList = components['schemas']['PaginatedTreasuredSubjectList'];

export type TreasuredSignoff = components['schemas']['TreasuredSignoff'];
export type TreasuredSignoffRequest = components['schemas']['TreasuredSignoffRequest'];
export type PaginatedTreasuredSignoffList = components['schemas']['PaginatedTreasuredSignoffList'];

export type VisibilityModeEnum = components['schemas']['VisibilityModeEnum'];

// ---------------------------------------------------------------------------
// Hand-authored types (#1771)
//
// `SceneLinesAndVeilsView` and `BeatStakeAvailabilityView` are plain APIViews
// that build their response from a bare `serializers.Serializer` (not a
// `serializer_class` on the view), so `drf-spectacular` cannot introspect the
// response body — the generated operation shows "No response body" for both.
// This mirrors the documented gotcha in `src/stories/types.ts` ("spectacular
// cannot introspect APIView-based dashboard endpoints"): the shapes below are
// authored by hand from `world.boundaries.serializers.SceneLinesAndVeilsSerializer`
// (Task 6) and must be kept in sync with it.
// ---------------------------------------------------------------------------

/** Anonymized shared PlayerBoundary (ADVISORY only — never a hard line, never an owner). */
export interface SharedAdvisoryBoundary {
  theme_name: string;
  detail: string;
}

/** Anonymized shared TreasuredSubject (never an owner). */
export interface SharedTreasuredSubject {
  subject_kind: string;
  subject_label: string;
  detail: string;
}

/** Scene "lines & veils" aggregate — GET /api/boundaries/scenes/{id}/lines-and-veils/. */
export interface SceneLinesAndVeils {
  advisories: SharedAdvisoryBoundary[];
  treasured_subjects: SharedTreasuredSubject[];
}
