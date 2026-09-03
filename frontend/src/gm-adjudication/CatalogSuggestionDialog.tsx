/**
 * CatalogSuggestionDialog: GM-facing "suggest a catalog entry" form (#3564).
 *
 * A GM who hits a gap in the discovery catalog (no situation kind fits, no
 * check is marked as fitting one, no difficulty or pool guidance exists yet)
 * can flag it here instead of improvising silently. The dialog dispatches the
 * existing `gm_submit_catalog_suggestion` REGISTRY action
 * (`actions/definitions/gm_adjudication.py`) over the generic REST dispatch
 * seam (`useDispatchPlayerAction`), the same pattern `GMAdjudicationPanel`
 * and `SummonPromptNotifier` use. Staff triage suggestions off-band; nothing
 * here writes the catalog directly, and trust-gated proposal kinds (e.g.
 * pool guidance) are refused server-side with a business-rule message this
 * dialog surfaces via toast and stays open on.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

const PROPOSAL_KINDS = [
  { value: 'new_situation', label: 'New situation kind' },
  { value: 'check_fit', label: 'A check that fits' },
  { value: 'difficulty_guide', label: 'Difficulty guide' },
  { value: 'pool_guide', label: 'Pool guidance' },
  { value: 'other', label: 'Other' },
] as const;

export interface CatalogSuggestionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  characterId: number;
  /** Pre-filled situation_kind_ref (a kind name) when the GM opened it from a kind card. */
  kindName?: string;
}

export function CatalogSuggestionDialog({
  open,
  onOpenChange,
  characterId,
  kindName,
}: CatalogSuggestionDialogProps) {
  const [proposalKind, setProposalKind] = useState<string>(PROPOSAL_KINDS[0].value);
  const [proposalText, setProposalText] = useState('');
  const [kindRef, setKindRef] = useState(kindName ?? '');
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit = proposalText.trim() !== '' && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    const trimmedRef = kindRef.trim();
    const kwargs: Record<string, unknown> = {
      proposal_kind: proposalKind,
      proposal_text: proposalText,
      ...(trimmedRef ? { situation_kind_ref: trimmedRef } : {}),
    };
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'gm_submit_catalog_suggestion' },
        kwargs,
      })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'The suggestion was refused.');
          return;
        }
        toast.success(result.message ?? 'Suggestion submitted.');
        onOpenChange(false);
      })
      .catch(() => toast.error('Could not submit the suggestion.'));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="suggestion-dialog">
        <DialogHeader>
          <DialogTitle>Suggest a catalog entry</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Staff review every suggestion. Some kinds need more GM trust than others.
        </p>
        <div className="space-y-1">
          <Label htmlFor="suggestion-proposal-kind">What kind of addition?</Label>
          <select
            id="suggestion-proposal-kind"
            data-testid="suggestion-proposal-kind"
            className={SELECT_CLASS}
            value={proposalKind}
            onChange={(e) => setProposalKind(e.target.value)}
          >
            {PROPOSAL_KINDS.map((kind) => (
              <option key={kind.value} value={kind.value}>
                {kind.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="suggestion-kind">Situation kind (optional)</Label>
          <Input
            id="suggestion-kind"
            data-testid="suggestion-kind"
            placeholder="e.g. Chase"
            value={kindRef}
            onChange={(e) => setKindRef(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="suggestion-text">Details</Label>
          <Textarea
            id="suggestion-text"
            data-testid="suggestion-text"
            placeholder="What should staff add or change?"
            value={proposalText}
            onChange={(e) => setProposalText(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button data-testid="suggestion-submit" disabled={!canSubmit} onClick={handleSubmit}>
            {dispatch.isPending ? 'Submitting…' : 'Submit suggestion'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
