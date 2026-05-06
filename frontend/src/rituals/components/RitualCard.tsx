/**
 * RitualCard — single ritual row in the Rituals list.
 *
 * Shows name, description, a snippet of narrative_prose, and a "Perform" button
 * that opens RitualPerformDialog. Pattern mirrors TableCard.tsx.
 */

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RitualPerformDialog } from './RitualPerformDialog';
import type { RitualWithSchema } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RitualCardProps {
  ritual: RitualWithSchema;
  characterSheetId: number;
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RitualCard({ ritual, characterSheetId, onSuccess }: RitualCardProps) {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <Card>
        <CardContent className="flex items-start justify-between gap-4 py-4">
          <div className="min-w-0 flex-1">
            <span className="text-base font-semibold">{ritual.name}</span>
            {ritual.description && (
              <p className="mt-1 text-sm text-muted-foreground">{ritual.description}</p>
            )}
            {ritual.narrative_prose && (
              <p className="mt-2 line-clamp-3 text-sm italic text-muted-foreground">
                {ritual.narrative_prose}
              </p>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0"
            onClick={() => setDialogOpen(true)}
          >
            Perform
          </Button>
        </CardContent>
      </Card>

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
    </>
  );
}
