/**
 * KinshipPanel — the character sheet's Kinship tab (#2062, #3003).
 *
 * Renders the family as a generation-layered graph (`KinTreeGraph`, ADR-0097 —
 * never a binary tree) plus a relatedness readout for whichever node is
 * selected.
 *
 * A tree node's `id` is a Kinsperson pk; the relationship endpoint's `a`/`b`
 * are CharacterSheet pks — a different id space. Most kin are unplayed NPCs
 * with no bound sheet at all, so a selection only gets a relatedness query
 * when its `sheet_id` is known (see `KinspersonNode` in `types.ts`); for
 * everyone else the panel says so honestly instead of guessing with the
 * wrong id.
 */
import { useState } from 'react';
import { Loader2 } from 'lucide-react';

import { useKinRelationship, useKinTree } from '../queries';
import type { KinspersonNode } from '../types';
import { KinTreeGraph } from './KinTreeGraph';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
}

export function KinshipPanel({ characterId }: Props) {
  const { data: tree, isLoading, isError } = useKinTree(characterId);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (isError) {
    return <p className="text-destructive">Failed to load the kin tree.</p>;
  }

  const nodes = tree?.nodes ?? [];
  if (nodes.length === 0) {
    return <p className="py-8 text-center text-muted-foreground">No recorded kin.</p>;
  }

  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <div className="space-y-4">
      {tree?.family && <p className="text-sm text-muted-foreground">House {tree.family.name}</p>}
      <div className="overflow-x-auto rounded-md border bg-card p-4">
        <KinTreeGraph
          nodes={nodes}
          parentage={tree?.parentage ?? []}
          unions={tree?.unions ?? []}
          selectedNodeId={selectedId}
          onSelectNode={(node) => setSelectedId(node.id)}
        />
      </div>
      {selectedNode && <SelectedKinDetail characterId={characterId} node={selectedNode} />}
    </div>
  );
}

interface SelectedKinDetailProps {
  characterId: number;
  node: KinspersonNode;
}

/**
 * A separate component so `useKinRelationship` is only ever called once a
 * node is selected (rules of hooks — this can't be a conditional call inside
 * `KinshipPanel` itself), matching the "query only fires once opened" idiom
 * already used for Radix tab content elsewhere on the sheet.
 */
function SelectedKinDetail({ characterId, node }: SelectedKinDetailProps) {
  const isSelf = node.sheet_id === characterId;
  const relatableSheetId = node.sheet_id != null && !isSelf ? node.sheet_id : undefined;
  const { data: relationship } = useKinRelationship(characterId, relatableSheetId);

  return (
    <div className="space-y-1 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{node.name}</span>
        <span className="text-xs text-muted-foreground">{node.tier.replace(/_/g, ' ')}</span>
      </div>
      {node.description && <p className="text-sm text-muted-foreground">{node.description}</p>}
      {isSelf ? (
        <p className="text-xs text-muted-foreground">This is the character you're viewing.</p>
      ) : relatableSheetId == null ? (
        <p className="text-xs text-muted-foreground">
          No linked character record for this person — relatedness can't be checked from here.
        </p>
      ) : (
        <p className="text-sm">
          {relationship?.label
            ? `Relationship: ${relationship.label.replace(/_/g, ' ')}`
            : 'No determinable relationship on record.'}
        </p>
      )}
    </div>
  );
}
