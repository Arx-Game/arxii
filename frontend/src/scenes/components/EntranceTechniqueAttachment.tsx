/**
 * EntranceTechniqueAttachment — technique+target attachment for a Make-an-Entrance
 * pose (#2183). Structurally mirrors `ActionAttachment.tsx`'s popover shape.
 *
 * Only meaningful while the ✨ entrance toggle is ON — `CommandInput` gates
 * whether this even mounts. Picking a technique with no `target_spec`
 * (self/no-target techniques) commits immediately; otherwise a `TargetPicker`
 * opens next. The result lifts to `CommandInput` as
 * `{ techniqueId, targetPersonaId? } | null`.
 */

import { useMemo, useState } from 'react';
import { Loader2, Wand2, X } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useCastableTechniques } from '../actionQueries';
import { TargetPicker, type TargetCandidate } from './TargetPicker';
import type { CastableTechnique } from '../actionTypes';

export interface EntranceTechniqueSelection {
  techniqueId: number;
  targetPersonaId?: number;
}

interface EntranceTechniqueAttachmentProps {
  /** The entering persona — resolves the castable-technique list. */
  personaId: number | null;
  /** Target candidates for techniques that need one — from the scene's participants. */
  candidates: TargetCandidate[];
  value: EntranceTechniqueSelection | null;
  onChange: (value: EntranceTechniqueSelection | null) => void;
}

export function EntranceTechniqueAttachment({
  personaId,
  candidates,
  value,
  onChange,
}: EntranceTechniqueAttachmentProps) {
  const [open, setOpen] = useState(false);
  const [pendingTechnique, setPendingTechnique] = useState<CastableTechnique | null>(null);

  const { data: techniques, isLoading } = useCastableTechniques(personaId);

  const attachedTechnique = useMemo(
    () => (value ? (techniques ?? []).find((t) => t.id === value.techniqueId) : undefined),
    [techniques, value]
  );

  function handlePick(technique: CastableTechnique) {
    if (technique.target_spec === null) {
      // Self/no-target technique — commits immediately, no picker step.
      onChange({ techniqueId: technique.id });
      setOpen(false);
      return;
    }
    // Keep the technique popover open while the TargetPicker is up — closing
    // it here makes Radix return focus to the trigger, which the picker's own
    // popover treats as an outside interaction and instantly self-dismisses
    // (same pattern as ActionPanel's targetingAction flow). Both close together
    // on confirm/cancel below.
    setPendingTechnique(technique);
  }

  function handleConfirmTarget(ids: number[]) {
    if (pendingTechnique && ids.length > 0) {
      onChange({ techniqueId: pendingTechnique.id, targetPersonaId: ids[0] });
    }
    setPendingTechnique(null);
    setOpen(false);
  }

  function handleCancelTarget() {
    setPendingTechnique(null);
    setOpen(false);
  }

  function handleDetach() {
    onChange(null);
  }

  const techniqueList = techniques ?? [];
  const hasTechniques = techniqueList.length > 0;

  return (
    <div className="flex items-center gap-1">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label="Attach entrance technique"
            title={value ? 'Click to detach entrance technique' : 'Attach entrance technique'}
            data-testid="entrance-technique-trigger"
            className={`flex h-6 w-6 items-center justify-center rounded text-xs hover:bg-accent hover:text-accent-foreground ${
              value ? 'bg-accent text-accent-foreground' : ''
            }`}
            onClick={(e) => {
              if (value) {
                e.preventDefault();
                handleDetach();
              }
            }}
          >
            <Wand2 className="h-3.5 w-3.5" />
          </button>
        </PopoverTrigger>
        <PopoverContent side="top" align="start" className="w-64 p-2">
          {isLoading && (
            <div className="flex items-center gap-2 p-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading...
            </div>
          )}
          {!isLoading && !hasTechniques && (
            <p className="p-2 text-sm text-muted-foreground">No castable techniques</p>
          )}
          {!isLoading && hasTechniques && (
            <div className="space-y-1">
              {techniqueList.map((technique) => (
                <button
                  key={technique.id}
                  type="button"
                  data-testid={`entrance-technique-option-${technique.id}`}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                  onClick={() => handlePick(technique)}
                >
                  <Wand2 className="h-3.5 w-3.5 shrink-0" />
                  <span className="flex-1 truncate">{technique.name}</span>
                  {technique.hostile && (
                    <span
                      className="text-xs text-destructive"
                      title="Hostile — may seed or feed a combat encounter"
                    >
                      ⚔
                    </span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {technique.anima_cost} anima
                  </span>
                </button>
              ))}
            </div>
          )}
        </PopoverContent>
      </Popover>

      {pendingTechnique && pendingTechnique.target_spec && (
        <TargetPicker
          spec={pendingTechnique.target_spec}
          candidates={candidates}
          onConfirm={handleConfirmTarget}
          onCancel={handleCancelTarget}
        />
      )}

      {value && (
        <button
          type="button"
          aria-label="Detach entrance technique"
          onClick={handleDetach}
          data-testid="entrance-technique-chip"
          className="flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground hover:bg-accent/80"
        >
          <Wand2 className="h-3 w-3" />
          {attachedTechnique?.name ?? `Technique #${value.techniqueId}`}
          <X className="ml-1 h-3 w-3" />
        </button>
      )}
    </div>
  );
}
