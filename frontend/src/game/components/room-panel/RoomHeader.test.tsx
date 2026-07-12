import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { RoomHeader } from './RoomHeader';

const SCENE = {
  id: 7,
  name: 'The Hall',
  description: '',
  is_owner: false,
  has_unseen_observer: false,
};

function renderHeader(props: { hasActiveEncounter?: boolean; hasActiveBattle?: boolean } = {}) {
  return render(
    <MemoryRouter>
      <RoomHeader
        name="The Hall"
        scene={SCENE}
        onStartScene={vi.fn()}
        onEndScene={vi.fn()}
        isStartPending={false}
        isEndPending={false}
        {...props}
      />
    </MemoryRouter>
  );
}

describe('RoomHeader combat/battle badges', () => {
  it('shows an In Combat badge linking to the scene (combat renders in-scene, #2197) when hasActiveEncounter is true', () => {
    renderHeader({ hasActiveEncounter: true });

    const badge = screen.getByTestId('room-header-combat-badge');
    expect(badge).toHaveTextContent('In Combat');
    expect(badge.closest('a')).toHaveAttribute('href', '/scenes/7');
  });

  it('shows a Battle badge linking to the battle map when hasActiveBattle is true', () => {
    renderHeader({ hasActiveBattle: true });

    const badge = screen.getByTestId('room-header-battle-badge');
    expect(badge).toHaveTextContent('Battle');
    expect(badge.closest('a')).toHaveAttribute('href', '/scenes/7/battle');
  });

  it('shows both badges together when both are active', () => {
    renderHeader({ hasActiveEncounter: true, hasActiveBattle: true });

    expect(screen.getByTestId('room-header-combat-badge')).toBeInTheDocument();
    expect(screen.getByTestId('room-header-battle-badge')).toBeInTheDocument();
  });

  it('shows neither badge by default', () => {
    renderHeader();

    expect(screen.queryByTestId('room-header-combat-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('room-header-battle-badge')).not.toBeInTheDocument();
  });
});
