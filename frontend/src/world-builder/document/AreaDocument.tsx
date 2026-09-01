/**
 * AreaDocument (#3477 Task 7) — "the manuscript pattern applies at every
 * altitude" (Dan's area-document ruling): the '✎ Edit' affordance on an
 * `AreaPage` opens this full-width document — the area's own prose plus
 * area-flavored marginalia — instead of a metadata dialog floating over the
 * map.
 *
 * Same outer-gate/inner-body split as `RoomDocument`, for the same reason:
 * `useDraft` seeds once at mount and never re-syncs from a prop change, so
 * the body must not mount until the manager payload holds real server
 * values. Draft fields are namespaced `area-name`/`area-description` because
 * the localStorage key's id segment is just a number — room 5 and area 5
 * would otherwise share a draft.
 *
 * The deep metadata (level, slug, realm/climate/society, color, permits)
 * stays in the reused #3269 `EditAreaDialog` behind the marginalia's
 * "✎ edit the record" door rather than being rebuilt as document fields:
 * those are catalog-backed bookkeeping edits, not prose, and the dialog
 * already carries their validation quirks (climate-below-REGION warning,
 * fixture-key slug freeze).
 */
import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { PlateHead } from '@/components/folio';
import { Textarea } from '@/components/ui/textarea';

import { EditAreaDialog } from '../components/EditAreaDialog';
import { ArtDialog } from './ArtDialog';
import { useAreaManagerQuery, useWorldBuilderAction } from '../queries';
import type { WorldBuilderActionKey, WorldBuilderAreaManager } from '../types';
import { useWorldBuilderActor } from '../useWorldBuilderActor';
import { useDraft } from './useDraft';

export interface AreaDocumentProps {
  areaId: number;
  /** Fires after a successful delete with the parent area id (null for a root). */
  onDeleted: (parentAreaId: number | null) => void;
}

export function AreaDocument({ areaId, onDeleted }: AreaDocumentProps) {
  const { data: manager } = useAreaManagerQuery(areaId);

  if (!manager) {
    return (
      <div className="p-8 text-sm text-muted-foreground" data-testid="area-document-loading">
        Loading the area…
      </div>
    );
  }

  return <AreaDocumentBody areaId={areaId} manager={manager} onDeleted={onDeleted} />;
}

function AreaDocumentBody({
  areaId,
  manager,
  onDeleted,
}: {
  areaId: number;
  manager: WorldBuilderAreaManager;
  onDeleted: (parentAreaId: number | null) => void;
}) {
  const area = manager.area;

  const characterId = useWorldBuilderActor();
  const { mutate: runMutation } = useWorldBuilderAction(characterId ?? 0, areaId);

  const runAction = (key: string, kwargs: Record<string, unknown>) => {
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation({ key: key as WorldBuilderActionKey, kwargs });
  };

  const nameDraft = useDraft(areaId, 'area-name', area.name);
  const descDraft = useDraft(areaId, 'area-description', area.description ?? '');

  const [metadataOpen, setMetadataOpen] = useState(false);
  const [artOpen, setArtOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const handleSave = () => {
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation(
      {
        key: 'edit_area',
        kwargs: { area_id: areaId, name: nameDraft.value, description: descDraft.value },
      },
      {
        onSuccess: (result) => {
          if (result.success !== false) {
            nameDraft.clearDraft();
            descDraft.clearDraft();
          }
        },
      }
    );
  };

  const handleDelete = () => {
    setDeleteConfirmOpen(false);
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation(
      { key: 'staff_remove_area', kwargs: { area_id: areaId } },
      {
        onSuccess: (result) => {
          if (result.success !== false) {
            onDeleted(area.parent ?? null);
          }
        },
      }
    );
  };

  return (
    <div className="grid grid-cols-[1fr_320px] gap-6 p-8" data-testid="area-document">
      <div>
        <div className="flex items-center gap-3">
          <input
            className="theme-heading min-w-0 flex-1 border-0 bg-transparent text-2xl [font-variant:small-caps] focus:outline-none"
            value={nameDraft.value}
            onChange={(event) => nameDraft.setValue(event.target.value)}
            aria-label="Area name"
            data-testid="area-name-input"
          />
          <PlateHead as="span" className="text-[0.65rem] tracking-wide" data-testid="area-level">
            {area.level_display}
          </PlateHead>
        </div>

        <Textarea
          className="mt-3 min-h-60 resize-y border-0 border-l font-body text-base leading-relaxed focus-visible:border-l-primary focus-visible:ring-0"
          value={descDraft.value}
          onChange={(event) => descDraft.setValue(event.target.value)}
          placeholder="Nothing written yet — what does this place feel like from above?"
          aria-label="Area description"
          data-testid="area-description-input"
        />

        <div
          className="mt-6 flex flex-wrap items-center gap-3 border-t pt-4"
          data-testid="area-document-savebar"
        >
          <span className="mr-auto font-body text-xs italic text-muted-foreground">
            draft kept as you type
          </span>
          <Button type="button" size="sm" onClick={handleSave} data-testid="area-save-button">
            Save
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={() => setDeleteConfirmOpen(true)}
            data-testid="area-delete-button"
          >
            delete…
          </Button>
        </div>
      </div>

      <AreaMarginalia
        manager={manager}
        onEditMetadata={() => setMetadataOpen(true)}
        onOpenArt={() => setArtOpen(true)}
      />

      <ArtDialog
        open={artOpen}
        onOpenChange={setArtOpen}
        subjectName={area.name}
        currentArtUrl={area.art_url}
        onHang={(mediaId) => runAction('edit_area', { area_id: areaId, art_id: mediaId })}
        onTakeDown={() => runAction('edit_area', { area_id: areaId, art_id: 0 })}
      />

      <EditAreaDialog
        area={area}
        catalogs={manager.catalogs}
        open={metadataOpen}
        onOpenChange={setMetadataOpen}
        runAction={runAction}
      />

      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {area.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes the area itself. An area still holding rooms or child areas refuses.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} data-testid="confirm-area-delete-button">
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Kv({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2 text-sm">
      <b className="font-medium">{term}</b>
      <span className="text-right text-muted-foreground">{children}</span>
    </div>
  );
}

/**
 * Area-flavored marginalia — read-only reads of what the manager payload
 * already carries (the same phase-1 boundary as the room `Marginalia`),
 * plus the one door: "✎ edit the record" into `EditAreaDialog`.
 */
function AreaMarginalia({
  manager,
  onEditMetadata,
  onOpenArt,
}: {
  manager: WorldBuilderAreaManager;
  onEditMetadata: () => void;
  onOpenArt: () => void;
}) {
  const area = manager.area;
  const climate = area.climate
    ? area.climate
    : area.effective_climate
      ? `${area.effective_climate} (inherited)`
      : 'unset';
  const roomsCount = manager.rooms.length;

  return (
    <aside aria-label="Area marginalia" className="flex flex-col" data-testid="area-marginalia">
      <div className="border-b pb-2 pt-2">
        <PlateHead as="h4" className="mb-1">
          The land
        </PlateHead>
        <Kv term="Realm">{area.realm ?? 'unset'}</Kv>
        <Kv term="Climate">{climate}</Kv>
      </div>

      <div className="border-b pb-2 pt-2">
        <PlateHead as="h4" className="mb-1">
          Society
        </PlateHead>
        <Kv term="Dominant">{area.dominant_society ?? 'none holds sway'}</Kv>
        <Kv term="Permits">{area.permit_eligibility || 'unset'}</Kv>
      </div>

      <div className="border-b pb-2 pt-2">
        <PlateHead as="h4" className="mb-1">
          Contents
        </PlateHead>
        <Kv term="Areas">{area.children_count}</Kv>
        <Kv term="Rooms">{roomsCount}</Kv>
      </div>

      <div className="border-b pb-2 pt-2">
        <PlateHead as="h4" className="mb-1">
          Art
        </PlateHead>
        {area.art_url ? (
          <img
            src={area.art_url}
            alt={`Art for ${area.name}`}
            className="max-h-32 w-full border object-cover"
            data-testid="area-art"
          />
        ) : (
          <p className="font-body text-sm text-muted-foreground">
            none hung — rooms beneath inherit whatever hangs above
          </p>
        )}
        <button
          type="button"
          className="mt-1 text-left font-body text-xs italic text-muted-foreground hover:text-primary"
          onClick={onOpenArt}
          data-testid="open-area-art-button"
        >
          ✎ hang art…
        </button>
      </div>

      <button
        type="button"
        className="mt-2 text-left font-body text-xs italic text-muted-foreground hover:text-primary"
        onClick={onEditMetadata}
        data-testid="edit-metadata-button"
      >
        ✎ edit the record (level, realm, climate, permits…)
      </button>
    </aside>
  );
}
