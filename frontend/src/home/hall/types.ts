import type { components } from '@/generated/api';

/**
 * `GET /api/clock/` (`world/game_clock/views.py::ClockViewSet.list`) — the
 * generated schema types this action's response as `ClockState[]` (a
 * drf-spectacular inference quirk on `viewsets.ViewSet` with no explicit
 * `many=` hint), but the view itself returns a single `Response(data)`
 * object (verified against source, #3412 T3 recon). This alias exists so
 * Hall code reads the true single-object shape rather than the
 * (mis-inferred) array the schema claims.
 */
export type ClockState = components['schemas']['ClockState'];

/**
 * `GET/PATCH /api/gm/profiles/mine/` (#3478 Task 1) — the requesting
 * account's own GM profile. `id`/`level`/`level_display` are read-only;
 * `contact_times`/`ooc_info` are the only writable fields, edited from the
 * Hall's GM slot (`EditGMProfileDialog`).
 */
export type GMProfileMine = components['schemas']['GMProfileMine'];
