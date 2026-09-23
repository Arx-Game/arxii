/**
 * RealmLeaf (#3983 Task 9, plate S-V "Fealty") — where the house stands:
 * sworn to, holds, demesne, and a vassals table with a "swear a house" door
 * that adds a new vassal beneath THIS house (`almanach_swear`,
 * `vassal_org_id` = the picked house, `liege_org_id` = this one).
 *
 * Every body field here is backend-derived and read-only (`_realm_payload`,
 * `almanach_reads.py`) — there's no realm-level prose or toggle to draft.
 * The savebar still carries `DRAFT_NOTE` (review fix round 1, Finding I3:
 * every savebar gets it per the global constraint) but no Save button next
 * to it — there is no staged field on this leaf for one to commit; "swear a
 * house" dispatches on its own dialog's Confirm, independent of any Save.
 *
 * One stated gap remains: the vassals table's `.tw` tier word (plate:
 * "county"/"duchy" before the name) has no field on `AlmanachRealmRowSummary`
 * to read — the row carries `title_id`/`name`/`held_by`/`demesne`/`vassals`,
 * no `tier`. The other two gaps this leaf used to carry are closed now that
 * `document.realm` carries `realm_id`/`default_tithe_pct` (final review I11
 * / deferred item 3): the "swear a house" dialog prefills its tithe percent
 * from `realm.default_tithe_pct`, and `HouseDocument`'s "the ladder" record
 * door links to `/staff/almanach/realms/:id` off `realm.realm_id`.
 *
 * The vassals table's house links, and the swear dialog's house picker, still
 * use `useAllHouses()` (unscoped — see `queries.ts`): the vassals table's own
 * rows carry names, not house ids, so the house link has to resolve by name
 * against the full house list regardless of realm scoping.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { useAllHouses } from '../queries';
import { DRAFT_NOTE } from '../copy';
import type { AlmanachDocumentRealm } from '../types';

export interface SwearFields {
  vassal_org_id: number;
  liege_org_id: number;
  tithe_pct?: number;
}

export interface RealmLeafProps {
  houseId: number;
  houseName: string;
  realm: AlmanachDocumentRealm;
  onSwear: (fields: SwearFields) => void;
}

function NumCell({ value }: { value: number }) {
  return <td className="n">{value > 0 ? value : <abbr title="none">—</abbr>}</td>;
}

function HeldByCell({ heldBy, heldById }: { heldBy: string; heldById: number | undefined }) {
  if (heldBy === '') return <span className="chip open">Unclaimed</span>;
  if (heldById != null) return <Link to={`/staff/almanach/houses/${heldById}`}>{heldBy}</Link>;
  return <>{heldBy}</>;
}

export function RealmLeaf({ houseId, houseName, realm, onSwear }: RealmLeafProps) {
  const [swearOpen, setSwearOpen] = useState(false);
  const { data: housesPayload } = useAllHouses();
  const houses = useMemo(
    () => (housesPayload?.results ?? []).filter((house) => house.id !== houseId),
    [housesPayload, houseId]
  );
  const houseIdByName = useMemo(
    () => new Map((housesPayload?.results ?? []).map((house) => [house.name, house.id])),
    [housesPayload]
  );

  const [vassalHouseId, setVassalHouseId] = useState('');
  const [tithePct, setTithePct] = useState('');

  const openSwear = () => {
    setVassalHouseId('');
    setTithePct(realm.default_tithe_pct != null ? String(realm.default_tithe_pct) : '');
    setSwearOpen(true);
  };

  const submitSwear = () => {
    if (vassalHouseId === '') return;
    onSwear({
      vassal_org_id: Number(vassalHouseId),
      liege_org_id: houseId,
      ...(tithePct.trim() !== '' ? { tithe_pct: Number(tithePct) } : {}),
    });
    setSwearOpen(false);
  };

  return (
    <>
      <main className="chapter">
        <h3>
          Realm <span className="tier">{houseName}</span>
        </h3>
        <div className="row3">
          <div className="field">
            <span className="label">sworn to</span>
            <div className="val">
              {realm.sworn_to !== '' ? realm.sworn_to : <abbr title="none">—</abbr>}
            </div>
          </div>
          <div className="field">
            <span className="label">holds</span>
            <div className="val">
              {realm.holds !== '' ? realm.holds : <abbr title="none">—</abbr>}
            </div>
          </div>
          <div className="field">
            <span className="label">demesne</span>
            <div className="val">
              {realm.demesne.length > 0 ? (
                <>
                  {realm.demesne.length} ·{' '}
                  {realm.demesne.map((row) => row.name || 'Undefined').join(', ')}
                </>
              ) : (
                <abbr title="none">—</abbr>
              )}
            </div>
          </div>
        </div>
        <div className="field">
          <span className="label">vassals</span>
          <div className="scroll">
            <table className="lad">
              <thead>
                <tr>
                  <th scope="col">vassal</th>
                  <th scope="col">held by</th>
                  <th scope="col" className="n">
                    demesne
                  </th>
                  <th scope="col" className="n">
                    vassals
                  </th>
                </tr>
              </thead>
              <tbody>
                {realm.vassals.map((row) => {
                  const heldById = houseIdByName.get(row.held_by);
                  return (
                    <tr key={row.title_id}>
                      <td>
                        {row.name !== '' ? row.name : <span className="chip undef">Undefined</span>}
                      </td>
                      <td>
                        <HeldByCell heldBy={row.held_by} heldById={heldById} />
                      </td>
                      <NumCell value={row.demesne} />
                      <NumCell value={row.vassals} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <div className="savebar">
          <span className="note">{DRAFT_NOTE}</span>
          <button type="button" className="btn quiet" onClick={openSwear}>
            swear a house
          </button>
        </div>
      </main>
      <Dialog
        open={swearOpen}
        onOpenChange={(next) => {
          if (!next) setSwearOpen(false);
        }}
      >
        <DialogContent className="almanach max-w-md">
          <DialogTitle>Swear a house</DialogTitle>
          <div className="field">
            <Label htmlFor="swear-house">house</Label>
            <Select value={vassalHouseId} onValueChange={setVassalHouseId}>
              <SelectTrigger id="swear-house">
                <SelectValue placeholder="pick a house" />
              </SelectTrigger>
              <SelectContent>
                {houses.map((house) => (
                  <SelectItem key={house.id} value={String(house.id)}>
                    {house.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="field">
            <Label htmlFor="swear-tithe">tithe percent</Label>
            <Input
              id="swear-tithe"
              type="number"
              min={0}
              max={100}
              value={tithePct}
              onChange={(event) => setTithePct(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSwearOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={submitSwear} disabled={vassalHouseId === ''}>
              Swear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
