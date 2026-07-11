/**
 * DramaticMomentSuggestionChip — GM confirm/dismiss inbox chip for PENDING
 * dramatic-moment suggestions anchored to a pose (#2183).
 *
 * Renders one amber chip per suggestion in `interaction.dramatic_moment_suggestions`
 * (already GM-gated server-side — empty for non-GM viewers, see
 * `world.scenes.interaction_serializers.get_dramatic_moment_suggestions`; `PoseUnit`
 * additionally gates the mount on `canGm` as defense in depth, mirroring the
 * "Tag moment" button). Confirm mints the `DramaticMomentTag` via the REGISTRY
 * action; dismiss discards the suggestion. Both invalidate `['scene-interactions',
 * sceneId]` — the same key `DramaticMomentTagDialog` invalidates.
 */

import { Check, X } from 'lucide-react';
import { useConfirmDramaticMomentSuggestion, useDismissDramaticMomentSuggestion } from '../queries';
import type { DramaticMomentSuggestionSummary } from '../types';

export interface DramaticMomentSuggestionChipProps {
  suggestions: DramaticMomentSuggestionSummary[];
  sceneId: string;
}

export function DramaticMomentSuggestionChip({
  suggestions,
  sceneId,
}: DramaticMomentSuggestionChipProps) {
  const confirmMutation = useConfirmDramaticMomentSuggestion(sceneId);
  const dismissMutation = useDismissDramaticMomentSuggestion(sceneId);

  if (suggestions.length === 0) return null;

  const isPending = confirmMutation.isPending || dismissMutation.isPending;

  return (
    <div className="mt-1 flex flex-wrap gap-1" data-testid="dramatic-moment-suggestions">
      {suggestions.map((suggestion) => (
        <span
          key={suggestion.id}
          data-testid="dramatic-moment-suggestion-chip"
          className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-xs text-amber-700 dark:text-amber-300"
        >
          ✶ {suggestion.moment_type_label}
          <button
            type="button"
            aria-label={`Confirm ${suggestion.moment_type_label}`}
            title="Confirm — mints the dramatic-moment tag"
            data-testid="dramatic-moment-suggestion-chip-confirm"
            disabled={isPending}
            onClick={() => confirmMutation.mutate(suggestion.id)}
            className="ml-1 rounded-full p-0.5 hover:bg-amber-500/20 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            type="button"
            aria-label={`Dismiss ${suggestion.moment_type_label}`}
            title="Dismiss this suggestion"
            data-testid="dramatic-moment-suggestion-chip-dismiss"
            disabled={isPending}
            onClick={() => dismissMutation.mutate(suggestion.id)}
            className="rounded-full p-0.5 text-muted-foreground hover:bg-muted disabled:opacity-50"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
