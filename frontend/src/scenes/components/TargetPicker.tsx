import { useState, useMemo } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import type { TargetSpec } from '../actionTypes';

/**
 * Subset of the Persona shape this picker actually reads.  The full generated
 * Persona schema is larger; we keep the local interface narrow so test
 * fixtures don't need to construct the entire model.
 */
export interface TargetCandidate {
  id: number;
  name: string;
  /**
   * Optional flag describing the candidate.  These fields are not currently
   * exposed on the generated Persona type — when they are, filtering kicks
   * in.  Until then, exclude_self and must_be_conscious are documented TODOs.
   */
  is_self?: boolean;
  is_conscious?: boolean;
}

interface TargetPickerProps {
  spec: TargetSpec;
  candidates: TargetCandidate[];
  onConfirm: (ids: number[]) => void;
  onCancel: () => void;
}

/**
 * Popover-based picker for selecting one or more targets to apply an action
 * against.  Single-cardinality specs commit on click; multi-cardinality specs
 * accumulate selections and commit on the Confirm button.
 *
 * The picker is opened-by-default and controlled by the parent: when the
 * picker closes (via confirm/cancel), the parent unmounts it.
 *
 * TODO(target-filters): the generated Persona type currently does not expose
 * `is_self` or `is_conscious` flags.  Filtering scaffolding is in place but
 * skipped when the candidate lacks the relevant flag — once the backend
 * surfaces these, no caller-side changes will be needed.
 */
export function TargetPicker({ spec, candidates, onConfirm, onCancel }: TargetPickerProps) {
  const isMulti = spec.cardinality === 'area' || spec.cardinality === 'filtered_group';
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const filteredCandidates = useMemo(() => {
    return candidates.filter((candidate) => {
      if (spec.filters.exclude_self && candidate.is_self === true) {
        return false;
      }
      if (spec.filters.must_be_conscious && candidate.is_conscious === false) {
        return false;
      }
      return true;
    });
  }, [candidates, spec.filters.exclude_self, spec.filters.must_be_conscious]);

  function handleSingleSelect(id: number) {
    onConfirm([id]);
  }

  function toggleMultiSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function handleConfirmMulti() {
    onConfirm(Array.from(selected));
  }

  // Controlled open — the parent unmounts us when picking is done, so we
  // wire up an open={true} popover with onOpenChange triggering cancel.
  return (
    <Popover
      open
      onOpenChange={(next) => {
        if (!next) onCancel();
      }}
    >
      <PopoverTrigger asChild>
        <span className="sr-only">Select target</span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72">
        <div className="space-y-3">
          <p className="text-sm font-medium">Select target{isMulti ? 's' : ''}</p>

          {filteredCandidates.length === 0 ? (
            <p className="text-xs text-muted-foreground">No valid targets.</p>
          ) : (
            <ul className="space-y-1">
              {filteredCandidates.map((candidate) => {
                if (!isMulti) {
                  return (
                    <li key={candidate.id}>
                      <button
                        type="button"
                        onClick={() => handleSingleSelect(candidate.id)}
                        className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm hover:bg-muted/50"
                      >
                        {candidate.name}
                      </button>
                    </li>
                  );
                }

                const isSelected = selected.has(candidate.id);
                return (
                  <li key={candidate.id}>
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={isSelected}
                      aria-pressed={isSelected}
                      onClick={() => toggleMultiSelect(candidate.id)}
                      className={`flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm hover:bg-muted/50 ${
                        isSelected ? 'bg-muted font-semibold' : ''
                      }`}
                    >
                      <span>{candidate.name}</span>
                      {isSelected && <span aria-hidden="true">✓</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            {isMulti && (
              <Button size="sm" onClick={handleConfirmMulti} disabled={selected.size === 0}>
                Confirm
              </Button>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
