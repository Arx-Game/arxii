/**
 * CombatMainMap shares cast-position picking with Your Turn (#4670): choosing a
 * position-shaped technique in the rail, then clicking a place on the main map,
 * sets the cast position.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CombatPickProvider } from '@/combat/CombatPickContext';
import { useCombatPick } from '@/combat/combatPick';
import { CombatMainMap } from '../CombatMainMap';

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn().mockReturnValue({
    data: [{ id: 1, name: 'Aerande', character_id: 10 }],
  }),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn().mockReturnValue('Aerande'),
}));

vi.mock('@/combat/components/CombatTacticalMap', () => ({
  CombatTacticalMap: ({
    characterId,
    positionShape,
    onPickPosition,
  }: {
    characterId: number;
    positionShape?: string;
    onPickPosition?: (id: number) => boolean;
  }) => (
    <div data-testid="combat-tactical-map" data-character-id={characterId}>
      <span data-testid="map-shape">{positionShape}</span>
      <button type="button" data-testid="map-place-5" onClick={() => onPickPosition?.(5)} />
    </div>
  ),
}));

function YourTurnStub() {
  const { castPosition, setPositionShape } = useCombatPick();
  return (
    <div>
      <button type="button" data-testid="pick-single" onClick={() => setPositionShape('single')} />
      <span data-testid="cast-destination">{String(castPosition.destinationId)}</span>
    </div>
  );
}

describe('CombatMainMap', () => {
  it('fills the cast position from a place click once a technique asks for one', async () => {
    const user = userEvent.setup();
    render(
      <CombatPickProvider encounterId={7}>
        <YourTurnStub />
        <CombatMainMap sceneId={1} encounterId={7} />
      </CombatPickProvider>
    );
    expect(screen.getByTestId('combat-tactical-map')).toHaveAttribute('data-character-id', '10');

    await user.click(screen.getByTestId('map-place-5'));
    expect(screen.getByTestId('cast-destination')).toHaveTextContent('undefined');

    await user.click(screen.getByTestId('pick-single'));
    expect(screen.getByTestId('map-shape')).toHaveTextContent('single');
    await user.click(screen.getByTestId('map-place-5'));
    expect(screen.getByTestId('cast-destination')).toHaveTextContent('5');

    await user.click(screen.getByTestId('map-place-5'));
    expect(screen.getByTestId('cast-destination')).toHaveTextContent('undefined');
  });

  it('clears picks when the encounter changes', async () => {
    const user = userEvent.setup();
    const tree = (id: number | null) => (
      <CombatPickProvider encounterId={id}>
        <YourTurnStub />
        <CombatMainMap sceneId={1} encounterId={7} />
      </CombatPickProvider>
    );
    const { rerender } = render(tree(7));
    await user.click(screen.getByTestId('pick-single'));
    await user.click(screen.getByTestId('map-place-5'));
    expect(screen.getByTestId('cast-destination')).toHaveTextContent('5');

    rerender(tree(null));
    expect(screen.getByTestId('cast-destination')).toHaveTextContent('undefined');
    expect(screen.getByTestId('map-shape')).toHaveTextContent('none');
  });
});
