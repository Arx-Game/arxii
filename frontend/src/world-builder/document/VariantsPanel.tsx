/**
 * VariantsPanel (#3477 Task 6) — the manuscript's "❧ variants" fold: the
 * FIRST UI for `staff_set_room_desc_variant`/`staff_remove_room_desc_variant`
 * (landed backend-only). Collapsed by default (the prototype's "winter,
 * night — add seasonal or day/night…" one-liner); expanding shows every
 * `desc_variants` row plus an add/edit form. A variant upserts on the
 * (room, season, phase) triple server-side, so editing an existing row keeps
 * its season/phase fixed (changing either would silently create a NEW row
 * instead of updating this one) — only a fresh "add" lets you pick them.
 */
import { useState } from 'react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import { SEASONS, TIME_PHASES, type WorldBuilderRoomDescVariant } from '../types';

export interface VariantsPanelProps {
  roomId: number;
  variants: WorldBuilderRoomDescVariant[];
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

interface DraftState {
  variantId: number | null;
  season: string;
  phase: string;
  description: string;
}

const BLANK_DRAFT: DraftState = { variantId: null, season: '', phase: '', description: '' };

function variantLabel(variant: WorldBuilderRoomDescVariant): string {
  return [variant.season, variant.phase].filter(Boolean).join(', ') || 'untitled';
}

export function VariantsPanel({ roomId, variants, runAction }: VariantsPanelProps) {
  const [draft, setDraft] = useState<DraftState>(BLANK_DRAFT);
  const [composing, setComposing] = useState(false);

  const summary = variants.length > 0 ? variants.map(variantLabel).join(', ') : 'none yet';

  const startEdit = (variant: WorldBuilderRoomDescVariant) => {
    setDraft({
      variantId: variant.id,
      season: variant.season ?? '',
      phase: variant.phase ?? '',
      description: variant.description,
    });
    setComposing(true);
  };

  const startAdd = () => {
    setDraft(BLANK_DRAFT);
    setComposing(true);
  };

  const save = () => {
    if (!draft.description.trim()) return;
    runAction('staff_set_room_desc_variant', {
      room_id: roomId,
      season: draft.season || undefined,
      phase: draft.phase || undefined,
      description: draft.description,
    });
    setComposing(false);
    setDraft(BLANK_DRAFT);
  };

  const remove = (variantId: number) => {
    runAction('staff_remove_room_desc_variant', { variant_id: variantId });
  };

  const editingExisting = draft.variantId != null;

  return (
    <Accordion type="single" collapsible data-testid="variants-panel">
      <AccordionItem value="variants" className="border-none">
        <AccordionTrigger className="py-1 font-body text-xs italic text-muted-foreground hover:no-underline">
          ❧ variants: <span data-testid="variants-summary">{summary}</span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="flex flex-col gap-2">
            {variants.map((variant) => (
              <div
                key={variant.id}
                className="flex items-baseline justify-between gap-2 border-b pb-1 text-sm"
                data-testid="variant-row"
              >
                <div>
                  <span className="theme-heading text-xs uppercase tracking-wide">
                    {variantLabel(variant)}
                  </span>
                  <p className="line-clamp-2 font-body text-xs text-muted-foreground">
                    {variant.description}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-primary"
                    onClick={() => startEdit(variant)}
                    data-testid="variant-edit"
                  >
                    edit
                  </button>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-destructive"
                    onClick={() => remove(variant.id)}
                    data-testid="variant-remove"
                  >
                    remove
                  </button>
                </div>
              </div>
            ))}

            {!composing && (
              <button
                type="button"
                className="text-left font-body text-xs italic text-muted-foreground hover:text-primary"
                onClick={startAdd}
                data-testid="variant-add-open"
              >
                add seasonal or day/night…
              </button>
            )}

            {composing && (
              <div className="flex flex-col gap-2 border-t pt-2" data-testid="variant-form">
                <div className="flex gap-2">
                  <Select
                    value={draft.season}
                    onValueChange={(value) => setDraft((prev) => ({ ...prev, season: value }))}
                    disabled={editingExisting}
                  >
                    <SelectTrigger className="flex-1" data-testid="variant-season">
                      <SelectValue placeholder="season (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      {SEASONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={draft.phase}
                    onValueChange={(value) => setDraft((prev) => ({ ...prev, phase: value }))}
                    disabled={editingExisting}
                  >
                    <SelectTrigger className="flex-1" data-testid="variant-phase">
                      <SelectValue placeholder="phase (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      {TIME_PHASES.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Textarea
                  value={draft.description}
                  onChange={(event) =>
                    setDraft((prev) => ({ ...prev, description: event.target.value }))
                  }
                  placeholder="what a visitor reads under these conditions"
                  data-testid="variant-description"
                />
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setComposing(false);
                      setDraft(BLANK_DRAFT);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={save}
                    disabled={!draft.description.trim()}
                    data-testid="variant-save"
                  >
                    Save
                  </Button>
                </div>
              </div>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
