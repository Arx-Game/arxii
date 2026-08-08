/**
 * AdvancementTab tests (#3045) — the isActiveCharacter gate.
 *
 * Every card underneath reads/writes through backend views resolved by the
 * account's puppeted character, not by an id passed from the sheet page —
 * this test pins that viewing an owned-but-inactive character shows the
 * switch-character notice instead of the (potentially wrong-character) cards.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { AdvancementTab } from './AdvancementTab';

vi.mock('./BreakthroughsCard', () => ({
  BreakthroughsCard: () => <div data-testid="mock-breakthroughs-card" />,
}));
vi.mock('./ClassUnlocksCard', () => ({
  ClassUnlocksCard: () => <div data-testid="mock-class-unlocks-card" />,
}));
vi.mock('./TrainingCard', () => ({
  TrainingCard: () => <div data-testid="mock-training-card" />,
}));
vi.mock('./DuranceCard', () => ({
  DuranceCard: () => <div data-testid="mock-durance-card" />,
}));

describe('AdvancementTab', () => {
  it('renders all four cards when viewing the active character', () => {
    renderWithProviders(<AdvancementTab characterId={10} isActiveCharacter />);

    expect(screen.getByTestId('advancement-tab')).toBeInTheDocument();
    expect(screen.getByTestId('mock-breakthroughs-card')).toBeInTheDocument();
    expect(screen.getByTestId('mock-class-unlocks-card')).toBeInTheDocument();
    expect(screen.getByTestId('mock-training-card')).toBeInTheDocument();
    expect(screen.getByTestId('mock-durance-card')).toBeInTheDocument();
  });

  it('shows a switch-character notice instead of the cards for an owned-but-inactive character', () => {
    renderWithProviders(<AdvancementTab characterId={10} isActiveCharacter={false} />);

    expect(screen.getByTestId('advancement-inactive-character-notice')).toBeInTheDocument();
    expect(screen.queryByTestId('advancement-tab')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mock-breakthroughs-card')).not.toBeInTheDocument();
  });
});
