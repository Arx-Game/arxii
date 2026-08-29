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
