import type { WorldBuilderPortalAnchor, WorldBuilderRoom } from '../types';
import { pairPortalAnchors } from './WorldCanvas';

const baseRoom: WorldBuilderRoom = {
  id: 1,
  name: 'Golden Hart Taproom',
  description: '',
  is_public: true,
  is_social_hub: true,
  is_outdoor: false,
  enclosure: 'walled',
  size_name: null,
  grid_x: 0,
  grid_y: 0,
  floor: 0,
  fixture_key: null,
  origin: 'authored',
  occupant_count: 0,
  clues: [],
  clue_triggers: [],
  portal_anchors: [],
};

function anchor(id: number, kindName: string, name = kindName): WorldBuilderPortalAnchor {
  return { id, kind_name: kindName, name, fixture_key: null };
}

function room(id: number, portalAnchors: WorldBuilderPortalAnchor[]): WorldBuilderRoom {
  return { ...baseRoom, id, portal_anchors: portalAnchors };
}

describe('pairPortalAnchors', () => {
  it('returns no records when there are no anchors', () => {
    expect(pairPortalAnchors([room(1, [])])).toEqual([]);
  });

  it('leaves a single anchor of a kind unpaired (no edge)', () => {
    expect(pairPortalAnchors([room(1, [anchor(10, 'Mirror')])])).toEqual([]);
  });

  it('pairs two anchors of the same kind, each pointing at the other room', () => {
    const rooms = [room(1, [anchor(10, 'Mirror')]), room(2, [anchor(11, 'Mirror')])];
    const records = pairPortalAnchors(rooms);
    expect(records).toHaveLength(2);
    const first = records.find((r) => r.id === 10);
    const second = records.find((r) => r.id === 11);
    expect(first).toMatchObject({ room_id: 1, kind_name: 'Mirror', destination_room_id: 2 });
    expect(second).toMatchObject({ room_id: 2, kind_name: 'Mirror', destination_room_id: 1 });
  });

  it('pairs the first two of three same-kind anchors and drops the third', () => {
    const rooms = [
      room(1, [anchor(10, 'Mirror')]),
      room(2, [anchor(11, 'Mirror')]),
      room(3, [anchor(12, 'Mirror')]),
    ];
    const records = pairPortalAnchors(rooms);
    expect(records).toHaveLength(2);
    expect(records.map((r) => r.id).sort()).toEqual([10, 11]);
    expect(records.some((r) => r.id === 12)).toBe(false);
  });

  it('pairs each kind independently with no cross-kind pairing', () => {
    const rooms = [
      room(1, [anchor(10, 'Mirror'), anchor(20, 'Well')]),
      room(2, [anchor(11, 'Mirror'), anchor(21, 'Well')]),
    ];
    const records = pairPortalAnchors(rooms);
    expect(records).toHaveLength(4);
    const mirrorRecords = records.filter((r) => r.kind_name === 'Mirror');
    const wellRecords = records.filter((r) => r.kind_name === 'Well');
    expect(mirrorRecords).toHaveLength(2);
    expect(wellRecords).toHaveLength(2);
    expect(mirrorRecords.find((r) => r.id === 10)?.destination_room_id).toBe(2);
    expect(mirrorRecords.find((r) => r.id === 11)?.destination_room_id).toBe(1);
    expect(wellRecords.find((r) => r.id === 20)?.destination_room_id).toBe(2);
    expect(wellRecords.find((r) => r.id === 21)?.destination_room_id).toBe(1);
  });
});
