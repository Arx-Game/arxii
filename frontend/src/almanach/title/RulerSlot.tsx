/**
 * The ruler slot (#5017): who holds a title in person, chosen from the holding
 * family's roll instead of searched for by name. Empty it reads Undefined ruler;
 * open it lists the family (members and their spouses, the dead last), narrowed
 * by typing, with Add family member at the foot; set it names the ruler as a
 * link and offers a change. The server's rule matches the roll: a member on
 * record or the wedded spouse of one.
 */
import { Pencil } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useAlmanachMutation, useHouseDocument } from '../queries';
import { personUrl } from '../shared/tier';
import type { AlmanachFamilyNode } from '../types';

interface RulerSlotProps {
  titleId: number;
  houseId: number;
  holderId: number | null;
  holderName: string;
}

function isDead(node: AlmanachFamilyNode) {
  return node.is_deceased || node.believed_deceased;
}

/** The words after a name on the roll: married in, rip, PC. */
function noteFor(node: AlmanachFamilyNode, familyId: number | null) {
  const notes: string[] = [];
  if (familyId != null && node.family_id !== familyId) notes.push('married in');
  if (isDead(node)) notes.push('rip');
  if (node.sheet_id != null) notes.push('PC');
  return notes.join(' · ');
}

export function RulerSlot({ titleId, houseId, holderId, holderName }: RulerSlotProps) {
  const { data: house } = useHouseDocument(houseId);
  const setHolder = useAlmanachMutation('almanach_set_holder');
  const createKin = useAlmanachMutation('almanach_create_kin');
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');

  const familyId = house?.family.family_id ?? null;
  const needle = q.trim().toLowerCase();
  const roll = (house?.family.nodes ?? [])
    .filter((node) => node.id !== holderId)
    .filter((node) => needle === '' || node.name.toLowerCase().includes(needle))
    .sort((a, b) => Number(isDead(a)) - Number(isDead(b)) || a.name.localeCompare(b.name));

  const close = () => {
    setOpen(false);
    setQ('');
    setAdding(false);
    setNewName('');
  };
  const pick = (nodeId: number) => {
    setHolder.mutate({ title_id: titleId, node_id: nodeId });
    close();
  };
  const add = () => {
    const name = newName.trim();
    if (familyId == null || name === '') return;
    createKin.mutate(
      { family_id: familyId, name },
      {
        onSuccess: (result) => {
          const made = result.data?.kinsperson_id;
          if (result.success === false || typeof made !== 'number') return;
          setHolder.mutate({ title_id: titleId, node_id: made });
        },
      }
    );
    close();
  };

  if (!open) {
    return holderId != null ? (
      <>
        <Link to={personUrl(holderId)}>{holderName}</Link>{' '}
        <button
          type="button"
          className="btn sm quiet icon"
          aria-label="Change ruler"
          title="Change ruler"
          onClick={() => setOpen(true)}
        >
          <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </>
    ) : (
      <button type="button" className="chip undef" onClick={() => setOpen(true)}>
        Undefined ruler
      </button>
    );
  }

  return (
    <div className="pick" role="group" aria-label="Ruler">
      <input
        type="search"
        className="rs"
        placeholder="Family member"
        aria-label="Family member"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <ul className="hits">
        {roll.map((node) => {
          const note = noteFor(node, familyId);
          return (
            <li key={node.id}>
              <button type="button" onClick={() => pick(node.id)}>
                {node.name}
                {note && <small> {note}</small>}
              </button>
            </li>
          );
        })}
        {roll.length === 0 && <li className="meta">none</li>}
        {familyId != null &&
          (adding ? (
            <li className="meta">
              <input
                type="text"
                className="rs"
                aria-label="Name"
                placeholder="Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    add();
                  }
                }}
              />{' '}
              <button
                type="button"
                className="btn sm quiet"
                disabled={newName.trim() === ''}
                onClick={add}
              >
                Add
              </button>
            </li>
          ) : (
            <li>
              <button type="button" className="new" onClick={() => setAdding(true)}>
                Add family member
              </button>
            </li>
          ))}
      </ul>
      <button type="button" className="btn sm ghost" onClick={close}>
        Cancel
      </button>
    </div>
  );
}
