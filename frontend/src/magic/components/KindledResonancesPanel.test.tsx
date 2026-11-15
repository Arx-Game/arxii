/**
 * KindledResonancesPanel tests (#5124): kindled rows say how strongly and why, an unkindled
 * row says so, and a character with no resonance sees nothing.
 */

import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { KindledResonance } from '@/magic/types';
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
  },
  {
    id: 2,
    name: 'Wonder',
    affinity_name: 'Primal',
    kindled: false,
    strength_name: null,
    reasons: [],
  },
];

describe('KindledResonancesPanel', () => {
  beforeEach(() => {
    vi.mocked(api.getKindledResonances).mockReset();
  });

  it('shows a kindled resonance with its strength word and reasons, and an unkindled one as not kindled', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue(rows);
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

  it('renders nothing for a character with no resonance', async () => {
    vi.mocked(api.getKindledResonances).mockResolvedValue([]);
    renderWithProviders(<KindledResonancesPanel characterSheetId={7} />);

    await vi.waitFor(() => expect(api.getKindledResonances).toHaveBeenCalled());
    expect(screen.queryByTestId('kindled-resonances-panel')).not.toBeInTheDocument();
  });
});
