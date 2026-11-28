/**
 * KindledResonancesPanel tests (#5124): kindled rows say how strongly and why, an unkindled
 * row says so, and a character with no resonance sees nothing.
 */

import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { Impulse, KindledResonance } from '@/magic/types';
import { KindledResonancesPanel } from './KindledResonancesPanel';

vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getKindledResonances: vi.fn(),
}));

import * as api from '@/magic/api';

const rows: KindledResonance[] = [
  {
    id: 1,
    name: 'Fury',
    affinity_name: 'Primal',
    kindled: true,
    strength_name: 'Blazing',
    reasons: ['The overseer who branded you is here.'],
    waiting_trickle: 0,
  },
  {
    id: 2,
    name: 'Wonder',
    affinity_name: 'Primal',
    kindled: false,
    strength_name: null,
    reasons: [],
    waiting_trickle: 9,
  },
];

const impulses: Impulse[] = [
  {
    resonance_id: 5,
    resonance_name: 'Ruin',
    label: 'Intrusive Thoughts: Ruin',
    present: false,
    is_compulsion: false,
    text: '',
    reasons: [],
  },
  {
    resonance_id: 6,
    resonance_name: 'Hunger',
    label: 'Intrusive Thoughts: Hunger',
    present: true,
    is_compulsion: false,
    text: 'The bread on the table is all you can think of.',
    reasons: ['A feast is laid out here.'],
  },
  {
    resonance_id: 7,
    resonance_name: 'Wrath',
    label: 'Compulsion: Wrath',
    present: false,
    is_compulsion: true,
    text: '',
    reasons: [],
  },
  {
    resonance_id: 8,
    resonance_name: 'Greed',
    label: 'Compulsion: Greed',
    present: true,
    is_compulsion: true,
    text: 'You cannot leave the coin on the table.',
    reasons: ['A purse sits unguarded.'],
  },
];

describe('KindledResonancesPanel', () => {
  beforeEach(() => {
    vi.mocked(api.getKindledResonances).mockReset();
  });

  it('shows a kindled resonance with its strength word and reasons, and an unkindled one as not kindled', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({ results: rows, impulses: [] });
    renderWithProviders(<KindledResonancesPanel characterSheetId={7} />);

    expect(await screen.findByText('Your resonances')).toBeInTheDocument();
    expect(screen.getByTestId('kindled-resonance-state-1')).toHaveTextContent('Kindled, blazing');
    expect(screen.getByText('The overseer who branded you is here.')).toBeInTheDocument();
    expect(screen.getByTestId('kindled-resonance-state-2')).toHaveTextContent('Not kindled');
    // The kindled tag is a pill; the unkindled state is plain muted text.
    expect(screen.getByTestId('kindled-resonance-state-1')).toHaveClass('rounded-full');
    expect(screen.getByTestId('kindled-resonance-state-2')).not.toHaveClass('rounded-full');
    expect(api.getKindledResonances).toHaveBeenCalledWith(7);
  });

  it("says how much the character's days have piled up for the anima ritual, only above zero", async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({ results: rows, impulses: [] });
    renderWithProviders(<KindledResonancesPanel characterSheetId={7} />);

    expect(await screen.findByTestId('kindled-resonance-trickle-2')).toHaveTextContent(
      '9 waiting for your anima ritual'
    );
    expect(screen.queryByTestId('kindled-resonance-trickle-1')).not.toBeInTheDocument();
  });

  it('renders nothing for a character with no resonance', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({ results: [], impulses: [] });
    renderWithProviders(<KindledResonancesPanel characterSheetId={7} />);

    await vi.waitFor(() => expect(api.getKindledResonances).toHaveBeenCalled());
    expect(screen.queryByTestId('kindled-resonances-panel')).not.toBeInTheDocument();
  });

  it('lists the impulses with their words, and sets a Compulsion costing rolls apart from one that only stirs', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({ results: rows, impulses });
    renderWithProviders(<KindledResonancesPanel characterSheetId={7} />);

    expect(await screen.findByText('Intrusive Thoughts: Ruin')).toBeInTheDocument();
    expect(screen.getByText('Intrusive Thoughts: Hunger')).toBeInTheDocument();
    expect(screen.getByText('The bread on the table is all you can think of.')).toBeInTheDocument();
    expect(screen.getByText('A feast is laid out here.')).toBeInTheDocument();
    expect(screen.getByText('Compulsion: Greed')).toBeInTheDocument();
    expect(screen.getByText('You cannot leave the coin on the table.')).toBeInTheDocument();

    expect(screen.getByTestId('impulse-5')).toHaveAttribute('data-state', 'stirring');
    expect(screen.getByTestId('impulse-6')).toHaveAttribute('data-state', 'stirring');
    expect(screen.getByTestId('impulse-7')).toHaveAttribute('data-state', 'compulsion');
    expect(screen.getByTestId('impulse-8')).toHaveAttribute('data-state', 'compulsion-active');
    // Only the Compulsion in effect is drawn heavy.
    expect(screen.getByTestId('impulse-8').className).toContain('border-2');
    expect(screen.getByTestId('impulse-7').className).not.toContain('border-2');
    // A quiet impulse has no words to show, so it shows only its name.
    expect(screen.getByTestId('impulse-5').querySelector('p')).toBeNull();
  });

  it('shows impulses even when the character holds no resonance, and no section when there are none', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue({
      results: [],
      impulses: [impulses[2]],
    });
    renderWithProviders(<KindledResonancesPanel characterSheetId={7} />);

    expect(await screen.findByText('Compulsion: Wrath')).toBeInTheDocument();
    expect(screen.queryByText('Your resonances')).not.toBeInTheDocument();
  });
});
