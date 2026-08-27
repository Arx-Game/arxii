/**
 * Hand-authored TS mirror of `world/battles/constants.py`'s `BattleActionKind`/
 * `BattleActionScope` TextChoices (#3389) — same convention as `BATTLE_RISK_LEVELS`
 * in `types.ts` (a backend enum with no OpenAPI schema representation of its own,
 * since it's read/written as a plain kwarg string on the generic dispatch
 * endpoint, not a serializer field). Not a new backend surface — keep these two
 * lists in sync with `constants.py` by hand when a kind/scope is added there.
 */

export type BattleActionKind =
  | 'strike'
  | 'support'
  | 'rescue'
  | 'rout'
  | 'rally'
  | 'repel'
  | 'hold'
  | 'breach'
  | 'fortify'
  | 'set_environment'
  | 'reposition'
  | 'move';

export const BATTLE_ACTION_KINDS: { value: BattleActionKind; label: string }[] = [
  { value: 'strike', label: 'Strike a unit' },
  { value: 'support', label: 'Support an ally' },
  { value: 'rescue', label: 'Rescue a surrounded ally' },
  { value: 'rout', label: 'Rout an enemy unit' },
  { value: 'rally', label: 'Rally an ally' },
  { value: 'repel', label: 'Repel an attack' },
  { value: 'hold', label: 'Hold or seize an objective' },
  { value: 'breach', label: 'Breach a fortification' },
  { value: 'fortify', label: 'Fortify a structure' },
  { value: 'set_environment', label: 'Set battlefield weather' },
  { value: 'reposition', label: 'Reposition a vehicle' },
  { value: 'move', label: 'Move to a front' },
];

export type BattleActionScope = 'unit' | 'place' | 'side' | 'battle';

export const BATTLE_ACTION_SCOPES: { value: BattleActionScope; label: string }[] = [
  { value: 'unit', label: 'Unit' },
  { value: 'place', label: 'Place (front-wide)' },
  { value: 'side', label: 'Side (army-wide)' },
  { value: 'battle', label: 'Battle (whole-battle-wide)' },
];

/**
 * Per-kind targeting shape (#3389 Design — "Target" bullet list). Drives which
 * target field(s) `BattleDeclarationSection` renders and which scope the kind
 * forces (when it forces one at all). Mirrors `declare_battle_action`'s own
 * per-kind validation (`world/battles/services.py`) — this is a client-side
 * *rendering* hint only; the server remains the actual authority.
 */
export type BattleActionTargetShape =
  | 'enemy_unit' // STRIKE, ROUT — target_unit filtered to the opposing side
  | 'ally' // SUPPORT, RESCUE, RALLY — target_ally filtered to the viewer's own side
  | 'place' // REPEL, HOLD, SET_ENVIRONMENT — target_place, scope forced to PLACE
  | 'fortification' // BREACH, FORTIFY — target_fortification, sourced from a place's fortifications
  | 'move' // MOVE — target_place (+ optional own-side target_unit for a commander order)
  | 'reposition'; // REPOSITION — target_place + reposition_dx/dy

export const BATTLE_ACTION_TARGET_SHAPES: Record<BattleActionKind, BattleActionTargetShape> = {
  strike: 'enemy_unit',
  rout: 'enemy_unit',
  support: 'ally',
  rescue: 'ally',
  rally: 'ally',
  repel: 'place',
  hold: 'place',
  set_environment: 'place',
  breach: 'fortification',
  fortify: 'fortification',
  move: 'move',
  reposition: 'reposition',
};
