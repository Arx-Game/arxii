/**
 * AlterationAuthorForm — author-from-scratch path of AlterationResolveDialog (#877).
 * Placeholder: implemented in the next task of this PR.
 */
import type { AlterationScratchPayload, AlterationTierCaps, PendingAlteration } from '../../types';

export interface AlterationAuthorFormProps {
  pending: PendingAlteration;
  caps: AlterationTierCaps;
  fieldErrors: Record<string, string[]>;
  isPending: boolean;
  onSubmit: (payload: AlterationScratchPayload) => void;
}

export function AlterationAuthorForm(_props: AlterationAuthorFormProps) {
  return null;
}
