/**
 * OwnRelationshipsList (#2159) — `RelationshipPanel`'s own-sheet arm.
 *
 * Lists the caller's outbound relationships (`CharacterRelationshipViewSet`,
 * `?source=<viewed CharacterSheet pk>` — already scoped server-side to the
 * caller's own tenure-owned characters, see ADR-0117): target name and
 * affection up front, each row expandable into per-track points/tiers
 * (`track_progress`, fetched via the detail retrieve — the list serializer
 * omits it) and the relationship's full history (Task 2's `?relationship=`
 * timeline arm), plus buttons opening `RelationshipWriteupDialog` in
 * development/capstone/redistribute modes.
 *
 * Row detail queries (`useRelationshipDetail`/`useRelationshipTimeline`) live
 * inside `AccordionContent`, which Radix only mounts once a row is expanded
 * — so this never fires N detail/timeline requests up front for N rows.
 */

import { useState } from 'react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useCharacterPersonasQuery } from '@/game/personaQueries';
import {
  useMyOutboundRelationships,
  useRelationshipDetail,
  useRelationshipTimeline,
} from '../queries';
import { RelationshipWriteupDialog } from './RelationshipWriteupDialog';
import type { RelationshipWriteupMode } from './RelationshipWriteupDialog';
import type { CharacterRelationshipList } from '../api';

export interface OwnRelationshipsListProps {
  characterSheetId?: number;
}

interface DialogRequest {
  targetCharacterSheetId: number;
  targetName: string;
  mode: RelationshipWriteupMode;
}

export function OwnRelationshipsList({ characterSheetId }: OwnRelationshipsListProps) {
  const { data: relationships = [], isLoading } = useMyOutboundRelationships(characterSheetId);
  const [dialogRequest, setDialogRequest] = useState<DialogRequest | null>(null);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading relationships…</p>;
  }

  if (relationships.length === 0) {
    return <p className="text-sm text-muted-foreground">No outbound relationships yet.</p>;
  }

  return (
    <div>
      <Accordion type="multiple">
        {relationships.map((relationship) => (
          <RelationshipRow
            key={relationship.id}
            relationship={relationship}
            onOpenDialog={(mode) =>
              setDialogRequest({
                targetCharacterSheetId: relationship.target,
                targetName: relationship.target_name,
                mode,
              })
            }
          />
        ))}
      </Accordion>

      {dialogRequest && (
        <TargetPersonaDialogLauncher
          request={dialogRequest}
          onOpenChange={(open) => {
            if (!open) setDialogRequest(null);
          }}
        />
      )}
    </div>
  );
}

function RelationshipRow({
  relationship,
  onOpenDialog,
}: {
  relationship: CharacterRelationshipList;
  onOpenDialog: (mode: RelationshipWriteupMode) => void;
}) {
  return (
    <AccordionItem value={String(relationship.id)}>
      <AccordionTrigger>
        <div className="flex flex-1 items-center justify-between pr-4 text-left">
          <span className="font-medium">{relationship.target_name}</span>
          <span className="text-sm text-muted-foreground">Affection {relationship.affection}</span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="mb-3 flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onOpenDialog('development')}
          >
            Develop
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onOpenDialog('capstone')}
          >
            Capstone
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onOpenDialog('redistribute')}
          >
            Redistribute
          </Button>
        </div>
        <RelationshipRowDetail relationshipId={relationship.id} />
      </AccordionContent>
    </AccordionItem>
  );
}

function RelationshipRowDetail({ relationshipId }: { relationshipId: number }) {
  const { data: detail } = useRelationshipDetail(relationshipId);
  const { data: history = [] } = useRelationshipTimeline({ relationship: relationshipId });

  return (
    <div className="space-y-4">
      <div>
        <h5 className="text-sm font-semibold">Tracks</h5>
        {detail && detail.track_progress.length > 0 ? (
          <ul className="mt-1 space-y-1">
            {detail.track_progress.map((track) => (
              <li key={track.track} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">{track.track_name}</span>
                <Badge variant="outline">{track.current_tier_name ?? 'No tier'}</Badge>
                <span className="text-muted-foreground">
                  {track.developed_points} developed / {track.capacity} capacity
                  {track.temporary_points ? ` (+${track.temporary_points} temp)` : ''}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No track progress yet.</p>
        )}
      </div>

      <div>
        <h5 className="text-sm font-semibold">History</h5>
        {history.length > 0 ? (
          <ul className="mt-1 space-y-2">
            {history.map((entry) => (
              <li key={`${entry.kind}-${entry.id}`} className="text-sm">
                <Badge variant="secondary" className="mr-2">
                  {entry.kind}
                </Badge>
                <span className="font-medium">{entry.title}</span>
                <span className="text-muted-foreground"> — {entry.track_name}</span>
                <p className="text-muted-foreground">{entry.writeup}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No history yet.</p>
        )}
      </div>
    </div>
  );
}

/**
 * Resolves the target CharacterSheet's persona (any persona bridges
 * server-side via `_resolve_target_sheet` — see `RelationshipWriteupDialog`'s
 * own docstring) before mounting the dialog, since `CharacterRelationshipList`
 * only carries the target's CharacterSheet pk, not a Persona pk. Renders
 * nothing until a persona resolves (or if the target genuinely has none).
 */
function TargetPersonaDialogLauncher({
  request,
  onOpenChange,
}: {
  request: DialogRequest;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: personas = [] } = useCharacterPersonasQuery(request.targetCharacterSheetId);
  const targetPersonaId =
    personas.find((p) => p.persona_type === 'primary')?.id ?? personas[0]?.id ?? null;

  if (targetPersonaId == null) {
    return null;
  }

  return (
    <RelationshipWriteupDialog
      open
      onOpenChange={onOpenChange}
      mode={request.mode}
      targetPersonaId={targetPersonaId}
      targetName={request.targetName}
    />
  );
}
