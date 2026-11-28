/**
 * GlimpseEditorDialog — the Glimpse editor mounted on the character sheet
 * (#2427 Task 6; answers final and saved on one confirm, #5292).
 *
 * Hosts the shared `GlimpseFlow`: catalog via `useGlimpseTags(pathId)` (the
 * same catalog CG's `GlimpseSection` reads, narrowed to the character's path
 * so The Choosing shows only to a path it belongs to), selection seeded from
 * the aura's current `glimpse_tags`/`glimpse_story`, writes through the aura
 * action mutations (`useSetGlimpseTags`/`useSetGlimpseProse`/
 * `useToggleGlimpseDistinction`, `@/magic/queries`).
 *
 * An answer gives its card when it is saved, and an answer written in play is
 * final for the player: the server refuses a second answer to a part
 * (`write_glimpse`), because a card is given back only through an approved
 * request. So a click here saves nothing. The picks are staged; "Save answers"
 * opens one confirm that names them and says they are final, and that confirm
 * sends them together. Before #5292 each click saved, which would have made a
 * misclick permanent. A part that already has its answer shows it and takes no
 * click. After a blackout The Reflection and Tone are not offered.
 *
 * `staff` (the staff sheet editor's door): every part is open, a saved answer
 * can be changed, and the confirm does not say the answers are final. The
 * server gives the new answer's card and leaves the old card in place.
 *
 * This mount's own link/unlink of the character's *existing* distinctions is a
 * different feature from the card an answer gives and stays, rendered via
 * `DistinctionLinkChips` below `GlimpseFlow`.
 *
 * ID-SPACE NOTE, read before touching `linkableDistinctions` /
 * `onToggleDistinctionLink`: this mount links by **CharacterDistinction row
 * id**, the id the aura's `link-glimpse-distinction`/
 * `unlink-glimpse-distinction` endpoints require (`character_distinction_id`),
 * which is exactly what `CharacterSheetDistinction.id` already carries (see
 * `world.character_sheets.serializers._build_distinctions`:
 * `DistinctionEntry(id=cd.pk, ...)`). Never pass a catalog Distinction id
 * here: the two id spaces are not interchangeable.
 */

import { useMemo, useState } from 'react';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useGlimpseTags } from '@/character-creation/queries';
import {
  useSetGlimpseProse,
  useSetGlimpseTags,
  useToggleGlimpseDistinction,
} from '@/magic/queries';
import type { CharacterSheetAura, CharacterSheetDistinction } from '@/character_sheets/api';
import { DistinctionLinkChips } from './DistinctionLinkChips';
import { AXIS_STEPS, GlimpseFlow } from './GlimpseFlow';
import type { GlimpseTagOption } from './glimpseTypes';

type Axis = GlimpseTagOption['axis'];

interface GlimpseEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** CharacterSheet pk — backs the character-sheet query invalidated after every write. */
  characterId: number;
  aura: CharacterSheetAura;
  /** The sheet payload's own `distinctions` list — no separate fetch (#2427 constraint). */
  distinctions: CharacterSheetDistinction[];
  /** The character's path, so the catalog offers only the answers that path may pick. */
  pathId?: number;
  /** Opened from the staff sheet editor: every part open, a saved answer changeable. */
  staff?: boolean;
}

/** The parts a blackout took, which the player is not offered. */
const BLACKOUT_AXES = new Set<Axis>(
  AXIS_STEPS.filter((step) => step.lostInBlackout).map((step) => step.axis)
);
const NO_AXES: ReadonlySet<Axis> = new Set<Axis>();

export function GlimpseEditorDialog({
  open,
  onOpenChange,
  characterId,
  aura,
  distinctions,
  pathId,
  staff = false,
}: GlimpseEditorDialogProps) {
  const { data: tags } = useGlimpseTags(pathId);
  const setTags = useSetGlimpseTags(aura.id, characterId);
  const setProse = useSetGlimpseProse(aura.id, characterId);
  const toggleDistinction = useToggleGlimpseDistinction(aura.id, characterId);

  const [prose, setProseDraft] = useState(aura.glimpse_story);
  // The picks not saved yet, by part. A part absent from the map shows what is saved.
  const [staged, setStaged] = useState<Partial<Record<Axis, number[]>>>({});
  const [confirming, setConfirming] = useState(false);

  const savedByAxis = useMemo(() => {
    const map = new Map<Axis, number[]>();
    for (const tag of aura.glimpse_tags) {
      // The sheet payload types the axis as a plain string.
      const axis = tag.axis as Axis;
      map.set(axis, [...(map.get(axis) ?? []), tag.id]);
    }
    return map;
  }, [aura.glimpse_tags]);

  // An answered part is final for the player; staff may change it.
  const closedAxes = useMemo(
    () => (staff ? NO_AXES : new Set<Axis>(savedByAxis.keys())),
    [staff, savedByAxis]
  );
  const hiddenAxes = !staff && aura.glimpse_memory === 'blacked_out' ? BLACKOUT_AXES : NO_AXES;

  const selectedTagIds = useMemo(() => {
    const ids: number[] = [];
    const axes = new Set<Axis>([...savedByAxis.keys(), ...(Object.keys(staged) as Axis[])]);
    for (const axis of axes) {
      ids.push(...(staged[axis] ?? savedByAxis.get(axis) ?? []));
    }
    return ids;
  }, [savedByAxis, staged]);

  // What the confirm will send: the staged parts that differ from what is saved.
  const changes = (Object.entries(staged) as [Axis, number[]][]).filter(([axis, ids]) => {
    const saved = savedByAxis.get(axis) ?? [];
    return ids.length !== saved.length || ids.some((id) => !saved.includes(id));
  });
  const tagName = (id: number) => (tags ?? []).find((tag) => tag.id === id)?.name ?? '';

  // Live-sheet linking is by CharacterDistinction row id (see file header).
  const linkedDistinctionIds = distinctions
    .filter((distinction) => distinction.is_from_glimpse)
    .map((distinction) => distinction.id);
  const linkableDistinctions = distinctions.map((distinction) => ({
    id: distinction.id,
    name: distinction.name,
  }));

  const handleChangeAxis = (axis: Axis, tagIds: number[]) => {
    setTags.reset();
    setStaged((current) => ({ ...current, [axis]: tagIds }));
  };

  const handleSaveAnswers = () => {
    setTags.mutate(
      { answers: changes.map(([axis, tagIds]) => ({ axis, tag_ids: tagIds })) },
      {
        onSuccess: () => {
          setStaged({});
          setConfirming(false);
        },
        onError: () => setConfirming(false),
      }
    );
  };

  const handleToggleDistinctionLink = (distinctionId: number) => {
    const isCurrentlyLinked = linkedDistinctionIds.includes(distinctionId);
    toggleDistinction.toggle(distinctionId, isCurrentlyLinked);
  };

  const proseDirty = prose !== aura.glimpse_story;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        {...NO_DESCRIPTION}
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        data-testid="glimpse-editor-dialog"
      >
        <DialogHeader>
          <DialogTitle>{staff ? 'The Glimpse' : 'Finish your Glimpse'}</DialogTitle>
        </DialogHeader>
        <GlimpseFlow
          tags={tags ?? []}
          selectedTagIds={selectedTagIds}
          prose={prose}
          onChangeAxis={handleChangeAxis}
          onChangeProse={setProseDraft}
          closedAxes={closedAxes}
          hiddenAxes={hiddenAxes}
        />
        {confirming ? (
          <div className="space-y-2 rounded border p-3 text-sm" data-testid="glimpse-confirm">
            <ul>
              {changes.map(([axis, tagIds]) => (
                <li key={axis}>
                  {AXIS_STEPS.find((step) => step.axis === axis)?.label.split(/[:;]/)[0] ?? axis}
                  {': '}
                  {tagIds.map(tagName).join(', ') || 'no answer'}
                </li>
              ))}
            </ul>
            {!staff && <p>These answers are final. A part you answer cannot be changed.</p>}
            <div className="flex gap-2">
              <Button
                type="button"
                onClick={handleSaveAnswers}
                disabled={setTags.isPending}
                data-testid="glimpse-confirm-save"
              >
                Save these answers
              </Button>
              <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                Keep choosing
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              onClick={() => setConfirming(true)}
              disabled={changes.length === 0}
              data-testid="glimpse-save-answers"
            >
              Save answers
            </Button>
            {setTags.isError && (
              <p className="text-sm text-destructive" role="alert">
                {setTags.error instanceof Error ? setTags.error.message : 'Not saved.'}
              </p>
            )}
          </div>
        )}
        <DistinctionLinkChips
          distinctions={linkableDistinctions}
          linkedIds={new Set(linkedDistinctionIds)}
          onToggle={handleToggleDistinctionLink}
          label="Link a distinction to your glimpse"
        />
        <DialogFooter>
          <Button
            type="button"
            onClick={() => setProse.mutate({ text: prose })}
            disabled={!proseDirty || setProse.isPending}
            data-testid="glimpse-save-story"
          >
            Save story
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
