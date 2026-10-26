/**
 * One holding on a rung's page (#4616): its name, kind, site and state, with the
 * three things staff do to it after adding it: rename, place it on a room, and
 * remove it (a second press confirms). Placing is offered for land holdings, which
 * stand on an outdoor room found by name; a farm's field and a building holding's
 * building have no finder here yet.
 */
import { useState } from 'react';

import { useRoomSearchQuery } from '@/world-builder/queries';

import { useAlmanachMutation } from '../queries';
import type { AlmanachHoldingKind, RungDocument } from '../types';

type Holding = RungDocument['holdings'][number];

export function HoldingRow({
  holding,
  kind,
}: {
  holding: Holding;
  kind: AlmanachHoldingKind | undefined;
}) {
  const rename = useAlmanachMutation('almanach_rename_holding');
  const site = useAlmanachMutation('almanach_site_holding');
  const remove = useAlmanachMutation('almanach_remove_holding');
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(holding.name);
  const [siting, setSiting] = useState(false);
  const [term, setTerm] = useState('');
  const [confirmRemove, setConfirmRemove] = useState(false);
  const { data: rooms } = useRoomSearchQuery(siting ? term : '');
  const label = holding.name || holding.kind;
  const canSite = kind?.site_kind === 'land' && !kind.requires_field;

  return (
    <tr>
      <td>
        {renaming ? null : label}
        {renaming && (
          <>
            <input
              type="text"
              aria-label={`name of ${label}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />{' '}
            <button
              type="button"
              className="btn sm quiet"
              aria-label={`Save name of ${label}`}
              disabled={name.trim() === '' || name.trim() === holding.name}
              onClick={() => {
                rename.mutate({ holding_id: holding.holding_id, name: name.trim() });
                setRenaming(false);
              }}
            >
              Save
            </button>
          </>
        )}
      </td>
      <td>{holding.kind}</td>
      <td>
        {holding.site || <span className="meta">none</span>}
        {siting && (
          <div className="pick">
            <input
              type="search"
              className="rs"
              placeholder="room"
              aria-label={`room for ${label}`}
              value={term}
              onChange={(e) => setTerm(e.target.value)}
            />
            {(rooms ?? []).length > 0 && (
              <ul className="hits">
                {(rooms ?? []).map((room) => (
                  <li key={room.id}>
                    <button
                      type="button"
                      onClick={() => {
                        site.mutate({ holding_id: holding.holding_id, room_id: room.id });
                        setSiting(false);
                        setTerm('');
                      }}
                    >
                      {room.name}
                      {room.area_name && <small> {room.area_name}</small>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </td>
      <td>{holding.unsited ? <span className="chip undef">unsited</span> : 'working'}</td>
      <td>
        <button
          type="button"
          className="add"
          aria-label={`Rename ${label}`}
          onClick={() => setRenaming((open) => !open)}
        >
          Rename
        </button>
        {canSite && (
          <>
            {' '}
            <button
              type="button"
              className="add"
              aria-label={`Site ${label}`}
              onClick={() => setSiting((open) => !open)}
            >
              Site
            </button>
          </>
        )}{' '}
        {confirmRemove ? (
          <>
            <button
              type="button"
              className="add"
              onClick={() => {
                remove.mutate({ holding_id: holding.holding_id });
                setConfirmRemove(false);
              }}
            >
              Confirm remove {label}
            </button>{' '}
            <button type="button" className="add" onClick={() => setConfirmRemove(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="add"
            aria-label={`Remove ${label}`}
            onClick={() => setConfirmRemove(true)}
          >
            Remove
          </button>
        )}
      </td>
    </tr>
  );
}
