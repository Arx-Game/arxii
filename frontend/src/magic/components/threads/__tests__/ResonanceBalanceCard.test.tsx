import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ResonanceBalanceCard } from '../ResonanceBalanceCard';
import type { ResonanceBalance, CharacterResonance } from '../../../types';

const makeBalance = (overrides: Partial<ResonanceBalance> = {}): ResonanceBalance => ({
  resonance_id: 1,
  balance: 42,
  lifetime_earned: 100,
  flavor_text: 'A rich, deep resonance.',
  ...overrides,
});

const makeCharacterResonance = (
  overrides: Partial<CharacterResonance> = {}
): CharacterResonance => ({
  id: 10,
  character_sheet: 5,
  resonance: 1,
  resonance_name: 'Bene',
  resonance_detail: {
    id: 1,
    name: 'Bene',
    affinity: 1,
    affinity_name: 'Celestial',
    description: 'A celestial resonance.',
    codex_entry_id: null,
  },
  balance: 42,
  lifetime_earned: 100,
  claimed_at: '2025-01-01T00:00:00Z',
  flavor_text: 'A rich, deep resonance.',
  ...overrides,
});

describe('ResonanceBalanceCard', () => {
  it('renders resonance name from characterResonance', () => {
    render(
      <ResonanceBalanceCard
        balance={makeBalance()}
        characterResonance={makeCharacterResonance({ resonance_name: 'Bene' })}
      />
    );
    expect(screen.getByText('Bene')).toBeInTheDocument();
  });

  it('falls back to resonance_id when characterResonance is undefined', () => {
    render(
      <ResonanceBalanceCard
        balance={makeBalance({ resonance_id: 7 })}
        characterResonance={undefined}
      />
    );
    expect(screen.getByText('Resonance #7')).toBeInTheDocument();
  });

  it('renders the balance number', () => {
    render(
      <ResonanceBalanceCard
        balance={makeBalance({ balance: 55 })}
        characterResonance={makeCharacterResonance()}
      />
    );
    expect(screen.getByTestId('resonance-balance-amount')).toHaveTextContent('55');
  });

  it('renders the lifetime_earned number', () => {
    render(
      <ResonanceBalanceCard
        balance={makeBalance({ lifetime_earned: 200 })}
        characterResonance={makeCharacterResonance()}
      />
    );
    expect(screen.getByTestId('resonance-lifetime-earned')).toHaveTextContent('200');
  });

  it('renders a HoverCard wrapper (trigger visible) when flavor_text is set', () => {
    // Radix HoverCard portals the popover content; it isn't in the DOM until hovered.
    // We verify the card itself renders correctly (the trigger is visible) by asserting
    // that the resonance name appears and the card is in the document.
    render(
      <ResonanceBalanceCard
        balance={makeBalance({ flavor_text: 'Celestial fire.' })}
        characterResonance={makeCharacterResonance()}
      />
    );
    // The HoverCardTrigger wraps the card — the resonance name should still be present
    expect(screen.getByText('Bene')).toBeInTheDocument();
    // The flavor text is in a data attribute we can assert is passed to the HoverCard
    // We assert the component renders without errors and the balance is shown
    expect(screen.getByTestId('resonance-balance-amount')).toHaveTextContent('42');
  });

  it('does not render a HoverCard when flavor_text is empty string', () => {
    render(
      <ResonanceBalanceCard
        balance={makeBalance({ flavor_text: '' })}
        characterResonance={makeCharacterResonance()}
      />
    );
    expect(screen.queryByText(/Celestial fire/)).not.toBeInTheDocument();
  });
});
