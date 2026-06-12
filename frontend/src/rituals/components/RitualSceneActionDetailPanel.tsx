/**
 * RitualSceneActionDetailPanel — detail panel for SCENE_ACTION rituals.
 *
 * Shows the ritual's narrative prose and a "Performable in scene" indicator.
 * When the caller is the ritual's author, shows an "Edit" button that opens
 * AnimaRitualEditDialog.
 *
 * Backend gap (Phase 9): The RitualSerializer does not yet fully surface
 * `check_config` (stat/skill/check_type) display in the UI.
 * The "Performable in scene" badge and edit button are rendered based on
 * execution_kind and author matching; the check spec (stat/skill/check_type)
 * display was deferred to a later phase.
 */

import { useState } from 'react';
import { Zap, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AnimaRitualEditDialog } from '@/magic/components/AnimaRitualEditDialog';
import type { RitualWithSchema } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RitualSceneActionDetailPanelProps {
  ritual: RitualWithSchema;
  /** The account id of the currently logged-in user; used to gate edit button. */
  currentAccountId: number | null;
  /** The author_account_id from the ritual — undefined until backend exposes it. */
  authorAccountId?: number | null;
  onEditSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RitualSceneActionDetailPanel({
  ritual,
  currentAccountId,
  authorAccountId,
  onEditSuccess,
}: RitualSceneActionDetailPanelProps) {
  const [editOpen, setEditOpen] = useState(false);

  // Show the Edit button only when we know the current user is the author.
  // When authorAccountId is undefined (backend gap), we cannot determine
  // authorship, so we conservatively hide the button.
  const isAuthor =
    currentAccountId !== null &&
    authorAccountId !== undefined &&
    authorAccountId !== null &&
    currentAccountId === authorAccountId;

  return (
    <>
      <div
        className="mt-3 rounded-md border border-indigo-800/40 bg-indigo-950/20 px-4 py-3"
        data-testid="ritual-scene-action-detail-panel"
      >
        {/* Performable in scene badge */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm text-indigo-400">
            <Zap className="h-4 w-4" />
            <span>Performable in scene</span>
          </div>

          {isAuthor && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1 text-xs"
              onClick={() => setEditOpen(true)}
              data-testid="ritual-edit-button"
            >
              <Pencil className="h-3 w-3" />
              Edit
            </Button>
          )}
        </div>

        {/* Check spec — not yet available until Phase 10 backend update */}
        <p className="mt-2 text-xs text-muted-foreground">
          Check spec (stat / skill / check type) will be shown once the frontend
          wires check_config fields.
        </p>

        {/* Narrative prose */}
        {ritual.narrative_prose && (
          <p className="mt-2 text-sm italic text-muted-foreground">{ritual.narrative_prose}</p>
        )}
      </div>

      {editOpen && (
        <AnimaRitualEditDialog
          ritual={ritual}
          open={editOpen}
          onOpenChange={setEditOpen}
          onSuccess={() => {
            setEditOpen(false);
            onEditSuccess?.();
          }}
        />
      )}
    </>
  );
}
