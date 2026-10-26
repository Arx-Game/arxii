import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PositionNodeLike } from '@/areas/components/TacticalMap';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { BattleMap } from './BattleMap';

type Feature = PositionNodeLike['features'][number];

function feature(id: number, name: string, overrides: Partial<Feature> = {}): Feature {
  return { id, name, art_url: null, square_x: null, square_y: null, ...overrides };
}

function place(id: number, name: string, overrides: Partial<PositionNodeLike>): PositionNodeLike {
  return {
    id,
    name,
    kind: 'primary',
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
    features: [],
    ...overrides,
  } as PositionNodeLike;
}

const FLOOR = place(1, 'Floor', {
  area_x: 2,
  area_y: 2,
  area_w: 10,
  area_h: 8,
  features: [
    feature(11, 'Chandelier', {
      art_url: 'https://example.com/chandelier.png',
      square_x: 6,
      square_y: 4,
    }),
    feature(12, 'rope'),
    // Outside the area (the area shrank after the feature was placed).
    feature(13, 'Balcony rail', { square_x: 40, square_y: 4 }),
  ],
});

function renderMap(onStepToSquare = vi.fn()) {
  render(
    <BattleMap
      nodes={[FLOOR]}
      edges={[]}
      occupantsByPosition={
        new Map([[1, [{ name: 'Malvaine', side: 'ally', square: { x: 3, y: 3 } }]]])
      }
      heldPositions={[]}
      moveActions={[]}
      ownPositionId={1}
      onDispatchMove={vi.fn()}
      onStepToSquare={onStepToSquare}
    />
  );
  return onStepToSquare;
}

describe('battle map features (#4675)', () => {
  it('draws a feature with art on its square, clipped to that square, named in a title', () => {
    renderMap();
    const mark = screen.getByTestId('battle-map-feature-11');
    expect(mark).toHaveAttribute('data-square', '6,4');
    expect(mark).toHaveAttribute('data-art', 'true');
    expect(mark.querySelector('title')).toHaveTextContent('Chandelier');
    const image = mark.querySelector('image')!;
    expect(image).toHaveAttribute('href', 'https://example.com/chandelier.png');
    expect(image).toHaveAttribute('width', '40');
    expect(image.getAttribute('clip-path')).toMatch(/^url\(#.+-feature-11\)$/);
  });

  it("draws a feature with no art as its name's initial", () => {
    renderMap();
    const mark = screen.getByTestId('battle-map-feature-12');
    expect(mark).not.toHaveAttribute('data-art');
    expect(mark.querySelector('text')).toHaveTextContent('R');
    expect(mark.querySelector('title')).toHaveTextContent('rope');
  });

  it('puts a feature with no square, or one outside its place, on the top-right squares', () => {
    renderMap();
    expect(screen.getByTestId('battle-map-feature-12')).toHaveAttribute('data-square', '11,2');
    expect(screen.getByTestId('battle-map-feature-13')).toHaveAttribute('data-square', '10,2');
  });

  it('draws features below the tokens and lets clicks reach the square beneath', () => {
    const onStepToSquare = renderMap();
    const layer = screen.getByTestId('battle-map-features');
    expect(layer).toHaveAttribute('pointer-events', 'none');
    const token = screen.getByTestId('occupant-token');
    expect(layer.compareDocumentPosition(token) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(screen.getByTestId('battle-map-square-1-6-4'));
    expect(onStepToSquare).toHaveBeenCalledWith({ x: 6, y: 4 });
  });

  it('stacks unplaced features leftwards and never past the area', () => {
    const nook = place(2, 'Nook', {
      area_x: 0,
      area_y: 0,
      area_w: 2,
      area_h: 1,
      features: [feature(21, 'A'), feature(22, 'B'), feature(23, 'C')],
    });
    render(
      <BattleMap
        nodes={[nook]}
        edges={[]}
        occupantsByPosition={new Map()}
        heldPositions={[]}
        moveActions={[]}
        ownPositionId={null}
        onDispatchMove={vi.fn()}
        onStepToSquare={vi.fn()}
      />
    );
    const squares = [21, 22, 23].map((id) =>
      screen.getByTestId(`battle-map-feature-${id}`).getAttribute('data-square')
    );
    expect(squares).toEqual(['1,0', '0,0', '0,0']);
  });
});
