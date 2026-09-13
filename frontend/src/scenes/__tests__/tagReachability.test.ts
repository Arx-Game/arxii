import { describe, it, expect } from 'vitest';
import { tagReachability } from '../tagReachability';
import type { RoomStateObject } from '@/hooks/types';

const serel: RoomStateObject = {
  dbref: '#2',
  name: 'Serel',
  thumbnail_url: null,
  commands: [],
  place_id: 5,
};
const vayne: RoomStateObject = {
  dbref: '#3',
  name: 'Vayne',
  thumbnail_url: null,
  commands: [],
  place_id: null,
};
const room = [serel, vayne];

describe('tagReachability', () => {
  it('is reachable for a whisper regardless of location', () => {
    const result = tagReachability(['Vayne'], room, 'whisper', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(true);
  });

  it("is reachable when the target shares the actor's current place", () => {
    const result = tagReachability(['Serel'], room, 'tt', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(true);
  });

  it('is unreachable when the target is at a different place in tt mode', () => {
    const result = tagReachability(['Vayne'], room, 'tt', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(false);
    expect(result.reason).toBe('Vayne is across the room and will not see table talk.');
    expect(result.hint).toBe(
      'Address the room to reach them, or send a whisper. Your draft is kept.'
    );
  });

  it('is reachable in a room-wide mode as long as the target is physically present', () => {
    const result = tagReachability(['Vayne'], room, 'pose', {
      isAtPlace: false,
      currentPlaceId: null,
      currentPlaceName: null,
    });
    expect(result.reachable).toBe(true);
  });

  it('is unreachable when the target is not in the room at all', () => {
    const result = tagReachability(['Someone Else'], room, 'pose', {
      isAtPlace: false,
      currentPlaceId: null,
      currentPlaceName: null,
    });
    expect(result.reachable).toBe(false);
    expect(result.reason).toBe('Someone Else is across the room and will not see table talk.');
  });

  it('resolves a name case-insensitively', () => {
    const result = tagReachability(['serel'], room, 'tt', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(true);
  });

  it("combines multiple unreachable names with the server's own grammar", () => {
    const result = tagReachability(['Vayne', 'Ghost'], room, 'tt', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(false);
    expect(result.reason).toBe('Vayne and Ghost are across the room and will not see table talk.');
  });

  it('is reachable when given no targets at all', () => {
    const result = tagReachability([], room, 'tt', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(true);
  });

  it('is reachable in pose mode even while the actor is seated at a place', () => {
    const result = tagReachability(['Vayne'], room, 'pose', {
      isAtPlace: true,
      currentPlaceId: 5,
      currentPlaceName: 'The Long Table',
    });
    expect(result.reachable).toBe(true);
  });
});
