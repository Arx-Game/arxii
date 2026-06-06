import type { components } from '@/generated/api';

export type RenownPayload = components['schemas']['Renown'];
export type FameBlock = components['schemas']['_Fame'];
export type PrestigeBreakdown = components['schemas']['_PrestigeBreakdown'];
export type SocietyReputationEntry = components['schemas']['_SocietyReputation'];
export type DeedEntry = components['schemas']['_Deed'];
export type RenownCardPayload = components['schemas']['RenownCard'];
export type RenownCardFame = components['schemas']['_RenownCardFame'];

/**
 * A persona that has a renown panel. PRIMARY and ESTABLISHED only —
 * TEMPORARY personas accumulate stats but don't get a sub-panel per spec.
 */
export interface RenownEligiblePersona {
  id: number;
  name: string;
  persona_type: 'primary' | 'established';
}
