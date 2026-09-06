/**
 * CompanionBondList (#3575) - the own-sheet relationship panel's companion block.
 *
 * Lists the viewer's bonded companions (`useMyCompanions`) with one button each:
 * "Record an impression" when no relationship toward that companion exists yet,
 * otherwise "Develop" (a companion bond is owner-only and active from creation,
 * so the branch is just "does a row exist"). Opens `RelationshipWriteupDialog`
 * with a companion target; later capstone/redistribute writes live on the
 * relationship row in `OwnRelationshipsList` like any other.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useMyCompanions } from '@/companions/queries';
import type { CompanionSummary } from '@/companions/types';
import type { CharacterRelationshipList } from '../api';
import { RelationshipWriteupDialog } from './RelationshipWriteupDialog';

export interface CompanionBondListProps {
  /** The caller's outbound relationships, to tell "no row yet" from "row exists". */
  relationships: CharacterRelationshipList[];
  onWritten?: () => void;
}

export function CompanionBondList({ relationships, onWritten }: CompanionBondListProps) {
  const { data: companions = [] } = useMyCompanions();
  const [pending, setPending] = useState<CompanionSummary | null>(null);
  const active = companions.filter((c) => c.released_at == null);

  if (active.length === 0) {
    return null;
  }

  const bondedIds = new Set(
    relationships.filter((r) => r.target_companion != null).map((r) => r.target_companion)
  );

  return (
    <div className="mb-4">
      <h3 className="mb-2 text-sm font-semibold">Companions</h3>
      <ul className="space-y-1">
        {active.map((companion) => {
          const hasBond = bondedIds.has(companion.id);
          return (
            <li key={companion.id} className="flex items-center justify-between">
              <span>
                {companion.name}
                <span className="ml-2 text-xs text-muted-foreground">
                  {companion.archetype.name}
                </span>
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid={`companion-bond-${companion.id}`}
                onClick={() => setPending(companion)}
              >
                {hasBond ? 'Develop' : 'Record an impression'}
              </Button>
            </li>
          );
        })}
      </ul>
      {pending && (
        <RelationshipWriteupDialog
          open
          onOpenChange={(open) => {
            if (!open) setPending(null);
          }}
          mode={bondedIds.has(pending.id) ? 'development' : 'impression'}
          target={{ kind: 'companion', companionId: pending.id }}
          targetName={pending.name}
          onSuccess={onWritten}
        />
      )}
    </div>
  );
}
