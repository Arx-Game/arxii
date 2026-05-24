/**
 * Shared types for the ActionDeclarationCard and related action UI.
 *
 * Lives in frontend/src/actions/ — a new top-level module used by both
 * scenes and combat. See docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §4.
 */

export type EffortLevel = 'VERY_LOW' | 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';

export type ActionSlot =
  | 'focused'
  | 'passive-physical'
  | 'passive-social'
  | 'passive-mental'
  | 'scene'; // single-card scene context

export interface ActionContext {
  slot: ActionSlot;
  /** Technique PK selected for this action. */
  techniqueId?: number;
  targetKind?: 'opponent' | 'ally' | 'social' | 'self';
  targetId?: number;
  effort: EffortLevel;
  strainCommitment: number;
}
