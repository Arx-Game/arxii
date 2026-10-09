/**
 * FamilyPage — one page per family, at /families/:id (#4209).
 *
 * Keyed by the Family pk (not an Organization pk: a commoner family has no org,
 * and every member has a family). Reads the family-keyed tree payload, which
 * already comes filtered to what the viewer may see, plus the CG slot browser's
 * open seats. Sections render or vanish: the gate (a plate for a house-styled
 * kind, with the house's words, colours and sigil; a plain head otherwise), the
 * family's own description, the roll grouped by generation in full-formal
 * names, the tree in short names, the selected person, the open seats.
 *
 * Names: the roll and the selected entry print `full_name`; the tree prints
 * `short_name`. No definition tier anywhere: a played person's name is a link to
 * their sheet, and that link is the only distinction a reader needs.
 *
 * The selected entry's relatedness is to the viewer's own selected character,
 * since the page has no subject; it prints only when a label comes back.
 */
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Skeleton } from '@/components/ui/skeleton';
import { useAccount } from '@/store/hooks';
import { urls } from '@/utils/urls';
import type { KinSlot, KinSlotPool } from '@/character-creation/types';
import { KinTreeGraph } from '../components/KinTreeGraph';
import { computeGenerations } from '../generations';
import { useFamilySlots, useFamilyTree, useKinRelationship } from '../queries';
import type { KinspersonNode, ParentageEdge } from '../types';
import '../family.css';

function paragraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

/** The roll's rows: one list per generation, the way the tree lays them out. */
function rollRows(nodes: KinspersonNode[], parentage: ParentageEdge[]): KinspersonNode[][] {
  const generation = computeGenerations(nodes, parentage);
  const byGeneration = new Map<number, KinspersonNode[]>();
  for (const node of nodes) {
    const gen = generation.get(node.id) ?? 0;
    byGeneration.set(gen, [...(byGeneration.get(gen) ?? []), node]);
  }
  return [...byGeneration.keys()]
    .sort((a, b) => a - b)
    .map((gen) =>
      (byGeneration.get(gen) ?? []).slice().sort((a, b) => a.short_name.localeCompare(b.short_name))
    );
}

/** A person's full-formal name with the dagger; a link when a sheet page exists. */
function PersonName({ node }: { node: KinspersonNode }) {
  const label = `${node.full_name}${node.is_deceased ? ' †' : ''}`;
  if (node.roster_entry_id != null) {
    return (
      <Link className="family-name" to={urls.character(node.roster_entry_id)}>
        {label}
      </Link>
    );
  }
  return <span className="family-name">{label}</span>;
}

interface SelectedEntryProps {
  node: KinspersonNode;
  /** The viewer's own selected character's sheet pk, or null without one. */
  viewerSheetId: number | null;
}

/**
 * A separate component so `useKinRelationship` is only ever called once a node
 * is selected. The query runs only when both sides have a sheet and they are
 * not the same person; the line prints only when a label comes back.
 */
function SelectedEntry({ node, viewerSheetId }: SelectedEntryProps) {
  const relatable =
    viewerSheetId != null && node.sheet_id != null && node.sheet_id !== viewerSheetId
      ? node.sheet_id
      : undefined;
  const { data: relationship } = useKinRelationship(viewerSheetId ?? -1, relatable);
  const label = relatable != null ? relationship?.label : null;
  return (
    <section className="family-selected" aria-label="Selected">
      <PersonName node={node} />
      {node.description && <p className="family-gloss">{node.description}</p>}
      {label && <p className="family-ledger">Related as {label.replace(/_/g, ' ')}.</p>}
    </section>
  );
}

function Seat({ slot }: { slot: KinSlot }) {
  return (
    <li className="family-seat">
      <span className="family-name">{slot.name || 'An open seat'}</span>
      <span className="family-chip">open</span>
      {slot.description && <p>{slot.description}</p>}
    </li>
  );
}

function Pool({ pool }: { pool: KinSlotPool }) {
  const name = pool.description || `Children of ${pool.parent_names.join(' and ')}`;
  const count = pool.count_remaining === 1 ? '1 seat' : `${pool.count_remaining} seats`;
  return (
    <li className="family-seat">
      <span className="family-name">{name}</span>
      <span className="family-count">{count}</span>
    </li>
  );
}

export function FamilyPage() {
  const { id } = useParams<{ id: string }>();
  const familyId = id !== undefined && /^\d+$/.test(id) ? Number(id) : undefined;
  return <FamilyPageInner familyId={familyId} />;
}

export function FamilyPageInner({ familyId }: { familyId: number | undefined }) {
  const { data: tree, isLoading, isError } = useFamilyTree(familyId);
  const { data: seats } = useFamilySlots(familyId);
  const account = useAccount();
  const viewerSheetId = account?.selected_entry?.character_id ?? null;
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const rows = useMemo(() => rollRows(tree?.nodes ?? [], tree?.parentage ?? []), [tree]);
  const nodes = tree?.nodes ?? [];
  const parentage = tree?.parentage ?? [];

  if (familyId == null || isError || (!isLoading && !tree?.family)) {
    return (
      <article className="family-page">
        <p className="family-empty">No family by that name is recorded.</p>
      </article>
    );
  }
  if (isLoading || !tree?.family) {
    return (
      <article className="family-page" aria-busy="true">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-40 w-full" />
      </article>
    );
  }

  const family = tree.family;
  const house = tree.house;
  const styled = family.kind.styles_as_house;
  const title = styled ? `House ${family.name}` : family.name;
  const eyebrow = [`${family.kind.name} ${styled ? 'House' : 'Family'}`, tree.realm_name]
    .filter(Boolean)
    .join(' · ');
  const arms = [
    house?.colors ? `Colours: ${house.colors}` : '',
    house?.sigil_description ? `Sigil: ${house.sigil_description}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
  const selected = nodes.find((n) => n.id === selectedId) ?? null;
  const slots = seats?.slots ?? [];
  const pools = seats?.pools ?? [];

  return (
    <article className="family-page">
      <header className={styled ? 'family-plate' : 'family-head'}>
        <span className="family-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {house?.words && <p className="family-words">“{house.words}”</p>}
        {arms && <p className="family-arms">{arms}</p>}
      </header>

      {family.description && (
        <section className="family-description" aria-label="Description">
          {paragraphs(family.description).map((text, index) => (
            <p key={index}>{text}</p>
          ))}
        </section>
      )}

      {nodes.length === 0 ? (
        <p className="family-empty">No kin on record.</p>
      ) : (
        <>
          <section className="family-section" aria-label="The roll">
            <h2>The roll</h2>
            {rows.map((row, index) => (
              <ul className="family-roll" key={index}>
                {row.map((node) => (
                  <li key={node.id}>
                    <PersonName node={node} />
                  </li>
                ))}
              </ul>
            ))}
          </section>

          <section className="family-tree" aria-label="The tree">
            <KinTreeGraph
              nodes={nodes}
              parentage={parentage}
              unions={tree.unions}
              selectedNodeId={selectedId}
              onSelectNode={(node) => setSelectedId(node.id)}
            />
          </section>

          {selected && <SelectedEntry node={selected} viewerSheetId={viewerSheetId} />}
        </>
      )}

      {(slots.length > 0 || pools.length > 0) && (
        <section className="family-section" aria-label="Open seats">
          <h2>Open seats</h2>
          <ul className="family-seats">
            {slots.map((slot) => (
              <Seat key={`slot-${slot.id}`} slot={slot} />
            ))}
            {pools.map((pool) => (
              <Pool key={`pool-${pool.id}`} pool={pool} />
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
