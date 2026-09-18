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
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): the graph keeps its frame, since a
 * drawing needs edges, but everything around it is ledger lines and entries.
 */
import { useState } from 'react';

import { useKinRelationship, useKinTree } from '../queries';
import { Entries, Entry, Ledger, Stack } from '@/character_sheets/components/sheet/primitives';
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
    return <Ledger>Reading their line…</Ledger>;
  }
  if (isError) {
    return (
      <p className="refsheet-ledger" style={{ color: 'hsl(var(--destructive))' }}>
        The kin tree could not be read.
      </p>
    );
  }

  const nodes = tree?.nodes ?? [];
  if (nodes.length === 0) {
    return <Ledger>No kin on record.</Ledger>;
  }

  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <Stack>
      {tree?.family && <Ledger>House {tree.family.name}</Ledger>}
      <div className="refsheet-plateau">
        <KinTreeGraph
          nodes={nodes}
          parentage={tree?.parentage ?? []}
          unions={tree?.unions ?? []}
          selectedNodeId={selectedId}
          onSelectNode={(node) => setSelectedId(node.id)}
        />
      </div>
      {selectedNode && <SelectedKinDetail characterId={characterId} node={selectedNode} />}
    </Stack>
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

  const relatedness = () => {
    if (isSelf) {
      return 'This is the character you are reading.';
    }
    if (relatableSheetId == null) {
      return 'Nobody on the roster answers to this person, so relatedness cannot be checked here.';
    }
    return relationship?.label
      ? `Related as ${relationship.label.replace(/_/g, ' ')}.`
      : 'No determinable relationship on record.';
  };

  return (
    <Entries>
      <Entry
        name={node.name}
        aside={<span className="refsheet-note">{node.tier.replace(/_/g, ' ')}</span>}
        gloss={node.description || undefined}
      >
        <Ledger>{relatedness()}</Ledger>
      </Entry>
    </Entries>
  );
}
