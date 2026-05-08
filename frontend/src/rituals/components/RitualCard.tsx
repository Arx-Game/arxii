/**
 * RitualCard — single ritual row in the Rituals list.
 *
 * Shows name, description, a snippet of narrative_prose, and an action button:
 *
 * - execution_kind === 'SCENE_ACTION': "Manage" button that expands a
 *   RitualSceneActionDetailPanel with check spec + edit controls.
 * - All other kinds: "Perform" button that opens RitualPerformDialog.
 *
 * Pattern mirrors TableCard.tsx.
 */

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RitualPerformDialog } from './RitualPerformDialog';
import { RitualSceneActionDetailPanel } from './RitualSceneActionDetailPanel';
import type { RitualWithSchema } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RitualCardProps {
  ritual: RitualWithSchema;
  characterSheetId: number;
  /** The account id of the currently logged-in user; forwarded to detail panel. */
  currentAccountId?: number | null;
  /** author_account_id from the ritual — undefined until backend exposes it. */
  authorAccountId?: number | null;
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isSceneAction(ritual: RitualWithSchema): boolean {
  return (ritual.execution_kind as string) === 'SCENE_ACTION';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RitualCard({
  ritual,
  characterSheetId,
  currentAccountId,
  authorAccountId,
  onSuccess,
}: RitualCardProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);

  const sceneAction = isSceneAction(ritual);

  return (
    <>
      <Card>
        <CardContent className="py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <span className="text-base font-semibold">{ritual.name}</span>
              {ritual.description && (
                <p className="mt-1 text-sm text-muted-foreground">{ritual.description}</p>
              )}
              {!sceneAction && ritual.narrative_prose && (
                <p className="mt-2 line-clamp-3 text-sm italic text-muted-foreground">
                  {ritual.narrative_prose}
                </p>
              )}
            </div>

            {sceneAction ? (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={() => setDetailOpen((prev) => !prev)}
                data-testid="ritual-manage-button"
              >
                Manage
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={() => setDialogOpen(true)}
              >
                Perform
              </Button>
            )}
          </div>

          {/* SCENE_ACTION detail panel (expanded inline) */}
          {sceneAction && detailOpen && (
            <RitualSceneActionDetailPanel
              ritual={ritual}
              currentAccountId={currentAccountId ?? null}
              authorAccountId={authorAccountId}
              onEditSuccess={() => {
                onSuccess?.();
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* Perform dialog — only for non-SCENE_ACTION rituals */}
      {!sceneAction && (
        <RitualPerformDialog
          ritual={ritual}
          characterSheetId={characterSheetId}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          onSuccess={() => {
            setDialogOpen(false);
            onSuccess?.();
          }}
        />
      )}
    </>
  );
}
