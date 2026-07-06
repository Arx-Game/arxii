import type { components } from '@/generated/api';

export type Battle = components['schemas']['BattleList'];
export type BattleDetail = components['schemas']['BattleDetail'];
export type BattleSide = components['schemas']['BattleSide'];
export type BattlePlace = components['schemas']['BattlePlace'];
export type BattleUnit = components['schemas']['BattleUnit'];
export type BattleParticipant = components['schemas']['BattleParticipant'];
export type PaginatedBattleListList = components['schemas']['PaginatedBattleListList'];

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
}
