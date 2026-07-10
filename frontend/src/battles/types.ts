import type { components } from '@/generated/api';

export type Battle = components['schemas']['BattleList'];
export type BattleDetail = components['schemas']['BattleDetail'];
export type BattleSide = components['schemas']['BattleSide'];
export type BattlePlace = components['schemas']['BattlePlace'];
export type BattleUnit = components['schemas']['BattleUnit'];
export type BattleParticipant = components['schemas']['BattleParticipant'];
export type PaginatedBattleListList = components['schemas']['PaginatedBattleListList'];

/**
 * Staging catalog types (#2010, Task 5's read-only REST) — admin-authored
 * blueprints/templates a GM stages a Battle from via the `create_battle`/
 * `stage_battle_map`/`spawn_battle_units` registry actions (StagingPanel).
 */
export type BattleMapBlueprint = components['schemas']['BattleMapBlueprint'];
export type PaginatedBattleMapBlueprintList =
  components['schemas']['PaginatedBattleMapBlueprintList'];
export type BattleUnitTemplate = components['schemas']['BattleUnitTemplate'];
export type PaginatedBattleUnitTemplateList =
  components['schemas']['PaginatedBattleUnitTemplateList'];

/**
 * `create_battle`'s `risk_level` kwarg (world/combat/constants.py RiskLevel,
 * mirrored here as the generated `RiskLevelEnum` — same 5 values already
 * used by `BattleDetail.risk_level`). No labels array: the staging form
 * derives a label by title-casing the value.
 */
export type BattleRiskLevel = components['schemas']['RiskLevelEnum'];
export const BATTLE_RISK_LEVELS: BattleRiskLevel[] = [
  'low',
  'moderate',
  'high',
  'extreme',
  'lethal',
];

/**
 * Payload for the ``battle_state`` WS message (world/web/webclient/message_types.py
 * ``BattleStatePayload``). Not part of the REST OpenAPI schema — this is a
 * hand-authored mirror of the backend dataclass, same convention as
 * ``RoulettePayload`` (components/roulette/types.ts). Carries no battle data
 * itself; it's a slim ping telling clients to refetch the REST aggregate.
 */
export interface BattleStatePayload {
  battle_id: number;
  round_number: number | null;
}

/**
 * BattleDetail nests a few backend dicts as untyped SerializerMethodField
 * output — OpenAPI can't describe an ad-hoc dict shape, so these fields come
 * through as ``{[key: string]: unknown} | null`` in the generated schema.
 * These interfaces mirror the exact keys `world/battles/serializers.py` emits
 * (BattleDetailSerializer.get_round, BattlePlaceSerializer.get_vehicle,
 * BattleParticipantSerializer.get_persona) — same convention as
 * `BattleStatePayload` above. Cast the loose field to these when reading it.
 */
export interface BattleRoundSummary {
  number: number;
  status: string;
}

export interface BattleVehicleSummary {
  unit_id: number;
  vehicle_kind: string;
  is_structural: boolean;
}

export interface BattlePersonaSummary {
  id: number;
  name: string;
  thumbnail_url: string | null;
  thumbnail_media_url: string | null;
}

/**
 * Hand-authored mirror of `BattleDeedSerializer`'s output (SerializerMethodField
 * — OpenAPI can't describe the ad-hoc dict shape). Same convention as
 * `BattleRoundSummary` / `BattlePersonaSummary` above. See #1735.
 */
export interface BattleDeed {
  id: number;
  title: string;
  description: string;
  base_value: number;
  created_at: string;
  persona: { id: number; name: string } | null;
}
