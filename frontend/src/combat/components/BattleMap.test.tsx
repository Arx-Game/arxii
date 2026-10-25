import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlayerAction } from '@/scenes/actionTypes';
import type { PositionEdgeLike, PositionNodeLike } from '@/areas/components/TacticalMap';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { BattleMap } from './BattleMap';
import type { BattleMapProps, BattleOccupant } from './BattleMap';

function place(
  id: number,
  name: string,
  overrides: Partial<PositionNodeLike> = {}
): PositionNodeLike {
  return {
    id,
    name,
    kind: 'feature',
    elevation_anchor_id: null,
    layout_x: null,
    layout_y: null,
    rampart_element: null,
    rampart_integrity: null,
    rampart_max_integrity: null,
    rampart_crack_state: null,
    is_roofed: false,
    screens_ranged: false,
    area_x: null,
    area_y: null,
    area_w: null,
    area_h: null,
    terrain_name: null,
    terrain_art_url: null,
    ...overrides,
  } as PositionNodeLike;
}

function moveAction(positionId: number): PlayerAction {
  return {
    backend: 'registry',
    display_name: 'Move',
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'registry',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: 'move_to_position',
      position_id: positionId,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

const FLOOR = place(1, 'Floor', { kind: 'primary', area_x: 2, area_y: 2, area_w: 4, area_h: 3 });
const STAGE = place(2, 'Stage', {
  area_x: 6,
  area_y: 2,
  area_w: 3,
  area_h: 3,
  terrain_name: 'Rug',
  terrain_art_url: 'https://example.com/rug.png',
});
// Built before areas: drawn from its layout point.
const DOORWAY = place(3, 'Doorway', { layout_x: -200, layout_y: 80 });
const AIR = place(4, 'Above Floor', { kind: 'aerial', elevation_anchor_id: 1 });
const EDGES: PositionEdgeLike[] = [
  {
    position_a_id: 1,
    position_b_id: 2,
    is_passable: true,
    blocks_flight: false,
    gating_challenge_name: null,
  },
  {
    position_a_id: 1,
    position_b_id: 3,
    is_passable: true,
    blocks_flight: false,
    gating_challenge_name: 'Locked Gate',
  },
];

function occupant(name: string, overrides: Partial<BattleOccupant> = {}): BattleOccupant {
  return { name, side: 'ally', square: null, ...overrides };
}

function renderMap(overrides: Partial<BattleMapProps> = {}) {
  const props: BattleMapProps = {
    nodes: [FLOOR, STAGE, DOORWAY, AIR],
    edges: EDGES,
    occupantsByPosition: new Map([
      [1, [occupant('Malvaine', { isViewer: true, square: { x: 3, y: 3 } })]],
      [2, [occupant('Harrow', { side: 'enemy', square: { x: 7, y: 3 } })]],
      [3, [occupant('Barkeep', { side: 'bystander', bystander: true })]],
      [4, [occupant('Liraveth')]],
    ]),
    heldPositions: [{ position_id: 2, holder_names: ['Harrow', 'Blade'] }],
    moveActions: [moveAction(2), moveAction(3), moveAction(4)],
    ownPositionId: 1,
    onDispatchMove: vi.fn(),
    onStepToSquare: vi.fn(),
    ...overrides,
  };
  render(<BattleMap {...props} />);
  return props;
}

describe('BattleMap', () => {
  beforeEach(() => vi.clearAllMocks());

  it('draws every combatant, including one in a place with no authored area and one in the air', () => {
    renderMap();
    for (const name of ['Malvaine', 'Harrow', 'Barkeep', 'Liraveth']) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }
    expect(screen.getByTestId('tactical-map-node-3')).toHaveAttribute('data-derived', 'true');
    const air = screen.getByTestId('tactical-map-node-4');
    expect(air).toHaveAttribute('aria-label', 'Above Floor: Liraveth');
    expect(within(air).getByTestId('occupant-token')).toHaveAttribute('data-aerial', 'true');
  });

  it('marks sides, the viewer and bystanders on their tokens', () => {
    renderMap();
    const tokens = screen.getAllByTestId('occupant-token');
    const byName = (name: string) => tokens.find((t) => t.textContent?.includes(name))!;
    expect(byName('Malvaine')).toHaveAttribute('data-viewer', 'true');
    expect(within(byName('Malvaine')).getByTestId('viewer-halo')).toBeInTheDocument();
    expect(byName('Harrow')).toHaveAttribute('data-side', 'enemy');
    expect(byName('Barkeep')).toHaveAttribute('data-bystander', 'true');
  });

  it('fills its box and centres the drawing', () => {
    renderMap();
    const svg = screen.getByTestId('battle-map');
    expect(svg).toHaveAttribute('width', '100%');
    expect(svg).toHaveAttribute('height', '100%');
    expect(svg).toHaveAttribute('preserveAspectRatio', 'xMidYMid meet');
  });

  it('labels a held place with its holders, on a line of its own', () => {
    renderMap({ heldPositions: [{ position_id: 2, holder_names: ['Harrow'] }] });
    // Stage is three squares wide: "Stage · Held by Harrow" would spill past it.
    expect(screen.getByText('Stage')).toBeInTheDocument();
    expect(screen.getByText('Held by Harrow')).toBeInTheDocument();
    expect(screen.queryByText(/Stage · Held/)).not.toBeInTheDocument();
    expect(screen.getByTestId('tactical-map-node-2')).toHaveAttribute('data-held', 'true');
  });

  it('fills a place with its terrain art and names a gate on its route', () => {
    renderMap();
    // Art of any shape covers its tile: no letterbox bands.
    const tile = screen.getByTestId('battle-map').querySelector('pattern image')!;
    expect(tile).toHaveAttribute('preserveAspectRatio', 'xMidYMid slice');
    expect(screen.getByTestId('battle-map-terrain-2').getAttribute('fill')).toMatch(/^url\(#/);
    expect(screen.getByTestId('battle-map-terrain-1').getAttribute('fill')).not.toMatch(/url/);
    expect(screen.getByTestId('battle-map-edge-1-3')).toHaveTextContent('Locked Gate');
  });

  it('cuts a name wider than its area, keeping the full text in its title', () => {
    renderMap({
      nodes: [place(9, 'The Long Gallery Stair', { area_x: 0, area_y: 0, area_w: 2, area_h: 3 })],
      edges: [],
      occupantsByPosition: new Map(),
      heldPositions: [{ position_id: 9, holder_names: ['Harrow'] }],
      moveActions: [],
    });
    const area = screen.getByTestId('tactical-map-node-9');
    const texts = [...area.querySelectorAll('text')].map((t) => t.textContent ?? '');
    expect(texts.every((t) => t.length * 6.6 + 8 <= 2 * 40 - 8)).toBe(true);
    expect(texts.some((t) => t.endsWith('…'))).toBe(true);
    expect(area.querySelector(':scope > title')).toHaveTextContent(
      'The Long Gallery Stair. Held by Harrow'
    );
    expect(area).toHaveAttribute('aria-label', 'The Long Gallery Stair');
  });

  it('draws no line for a plain route between touching places', () => {
    renderMap();
    // Floor (2..6) and Stage (6..9) share a border.
    expect(screen.queryByTestId('battle-map-edge-1-2')).not.toBeInTheDocument();
  });

  it('draws a gated route even between places that touch', () => {
    renderMap({
      edges: [{ ...EDGES[0], gating_challenge_name: 'Velvet Rope' }],
    });
    expect(screen.getByTestId('battle-map-edge-1-2')).toBeInTheDocument();
    expect(screen.getByTestId('battle-map-route-label-1-2')).toHaveTextContent('Velvet Rope');
  });

  it('draws a plain route between places that do not touch', () => {
    renderMap({
      nodes: [FLOOR, place(5, 'Balcony', { area_x: 2, area_y: 8, area_w: 3, area_h: 2 })],
      edges: [
        {
          position_a_id: 1,
          position_b_id: 5,
          is_passable: true,
          blocks_flight: false,
          gating_challenge_name: null,
        },
      ],
      occupantsByPosition: new Map(),
      heldPositions: [],
    });
    expect(screen.getByTestId('battle-map-edge-1-5')).toBeInTheDocument();
  });

  it('steps to a square in the viewer’s own place', () => {
    const props = renderMap();
    fireEvent.click(screen.getByTestId('battle-map-square-1-5-4'));
    expect(props.onStepToSquare).toHaveBeenCalledWith({ x: 5, y: 4 });
    expect(props.onDispatchMove).not.toHaveBeenCalled();
  });

  it('moves to the clicked square of a place a move reaches', () => {
    const props = renderMap();
    fireEvent.click(screen.getByTestId('battle-map-square-2-8-4'));
    expect(props.onDispatchMove).toHaveBeenCalledWith(props.moveActions[0], { x: 8, y: 4 });
  });

  it('moves into a place with no authored area without a square', () => {
    const props = renderMap();
    const door = screen.getByTestId('tactical-map-node-3');
    const square = door.querySelector('[data-testid^="battle-map-square-3-"]')!;
    fireEvent.click(square);
    expect(props.onDispatchMove).toHaveBeenCalledWith(props.moveActions[1], null);
  });

  it('moves into the air from its chip', () => {
    const props = renderMap();
    fireEvent.click(screen.getByTestId('battle-map-air-chip-4'));
    expect(props.onDispatchMove).toHaveBeenCalledWith(props.moveActions[2], null);
  });

  it('moves to a place with Enter, without a square', () => {
    const props = renderMap();
    fireEvent.keyDown(screen.getByTestId('tactical-map-node-2'), { key: 'Enter' });
    expect(props.onDispatchMove).toHaveBeenCalledWith(props.moveActions[0], null);
  });

  it('refuses a place no move reaches', () => {
    const props = renderMap({ moveActions: [] });
    fireEvent.click(screen.getByTestId('battle-map-square-2-8-4'));
    expect(props.onDispatchMove).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("You can't move there this turn.");
  });

  it('shows a gate’s name on its route', () => {
    renderMap();
    expect(screen.getByTestId('battle-map-route-label-1-3')).toHaveTextContent('Locked Gate');
  });

  it('keeps mark titles reachable and reads them in the place’s label', () => {
    renderMap({
      occupantsByPosition: new Map([
        [
          1,
          [
            occupant('Malvaine', {
              square: { x: 3, y: 3 },
              marks: [{ kind: 'locked', title: 'Malvaine: locked with Harrow' }],
            }),
            occupant('Bram'),
          ],
        ],
      ]),
    });
    const mark = screen.getByTestId('occupant-mark-locked');
    expect(mark).toHaveAttribute('pointer-events', 'auto');
    expect(mark.querySelector('title')).toHaveTextContent('Malvaine: locked with Harrow');
    expect(screen.getByTestId('tactical-map-node-1')).toHaveAttribute(
      'aria-label',
      'Floor: Malvaine (locked with Harrow), Bram'
    );
  });

  it('draws a lock link to someone in the air, from its anchor', () => {
    renderMap({
      links: [
        { id: 'lock-9', positionAId: 4, positionBId: 2, label: 'Liraveth locked with Harrow' },
      ],
    });
    const link = screen.getByTestId('battle-map-link-lock-9');
    expect(link).toHaveAttribute('aria-label', 'Liraveth locked with Harrow');
    // Never a click target: a click on the line reaches the square beneath.
    expect(link).toHaveAttribute('pointer-events', 'none');
  });

  it('does nothing on a click of the viewer’s own square', () => {
    const props = renderMap();
    fireEvent.click(screen.getByTestId('battle-map-square-1-3-3'));
    const tokens = screen.getAllByTestId('occupant-token');
    fireEvent.click(tokens.find((t) => t.textContent?.includes('Malvaine'))!);
    expect(props.onStepToSquare).not.toHaveBeenCalled();
    expect(props.onDispatchMove).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('moves with no square when a token in a target place is clicked', () => {
    const props = renderMap();
    const tokens = screen.getAllByTestId('occupant-token');
    fireEvent.click(tokens.find((t) => t.textContent?.includes('Harrow'))!);
    expect(props.onDispatchMove).toHaveBeenCalledWith(props.moveActions[0], null);
  });

  it('says a place with no authored area has no squares when the viewer stands in it', () => {
    const props = renderMap({ ownPositionId: 3 });
    const square = screen
      .getByTestId('tactical-map-node-3')
      .querySelector('[data-testid^="battle-map-square-3-"]')!;
    fireEvent.click(square);
    expect(props.onStepToSquare).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('This place has no squares to pick.');
  });

  it('hands a click to position picking first', () => {
    const onPickPosition = vi.fn(() => true);
    const props = renderMap({ onPickPosition });
    fireEvent.click(screen.getByTestId('battle-map-square-2-8-4'));
    expect(onPickPosition).toHaveBeenCalledWith(2);
    expect(props.onDispatchMove).not.toHaveBeenCalled();
  });

  it('hands a click to GM placement before moving', () => {
    const onGMPlace = vi.fn(() => true);
    const props = renderMap({ onGMPlace });
    fireEvent.click(screen.getByTestId('battle-map-square-1-5-4'));
    expect(onGMPlace).toHaveBeenCalledWith(1);
    expect(props.onStepToSquare).not.toHaveBeenCalled();
  });
});
