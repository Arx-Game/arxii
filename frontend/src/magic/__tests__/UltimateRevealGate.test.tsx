/**
 * Coverage for the Audere ultimate reveal + choice ceremony (#4098):
 * UltimateRevealGate + UltimateRevealDialog with real hooks
 * (useAudereUltimates / useChooseUltimate) and a mocked api transport — same
 * pattern as AudereOfferDialog.test.tsx.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { UltimateRevealGate } from '../components/UltimateRevealGate';
import type { AudereUltimateState } from '../types';

vi.mock('../api', () => ({ getAudereUltimates: vi.fn(), chooseUltimate: vi.fn() }));
import * as api from '../api';

const OPEN: AudereUltimateState = {
  reveal: {
    ceremony: 'audere',
    framing_text: 'PLACEHOLDER framing',
    groups: [
      {
        source: 'owned',
        path_name: 'Path of Steel',
        gift_name: 'Fire',
        being_name: '',
        companion_name: '',
        cards: [
          {
            choice_key: 'known:4',
            kind: 'known',
            category: 'shield',
            label: 'Wall',
            name: 'Ember Ward',
            description: 'A ward over the party',
            upgrade_of_name: '',
          },
          {
            choice_key: 'category:owned:2:sword',
            kind: 'category',
            category: 'sword',
            label: 'Edge',
            name: '',
            description: '',
            upgrade_of_name: '',
          },
        ],
      },
    ],
  },
  readied: null,
  deferred_death_text: '',
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('UltimateRevealGate', () => {
  beforeEach(() => vi.resetAllMocks());

  it('shows known by name and undiscovered by label only, never the raw category', async () => {
    vi.mocked(api.getAudereUltimates).mockResolvedValue(OPEN);
    render(
      <UltimateRevealGate characterSheetId={3} characterId={3} encounterId={1} isCeremonyActive />,
      {
        wrapper,
      }
    );
    expect(await screen.findByText('Ember Ward')).toBeInTheDocument();
    expect(screen.getByText('Edge')).toBeInTheDocument();
    expect(screen.queryByText(/sword/i)).not.toBeInTheDocument();
  });

  it('chooses the selected card', async () => {
    vi.mocked(api.getAudereUltimates).mockResolvedValue(OPEN);
    vi.mocked(api.chooseUltimate).mockResolvedValue({
      technique_id: 9,
      name: 'Cinder Crown',
      description: 'One strike',
      label: 'Edge',
    });
    render(
      <UltimateRevealGate characterSheetId={3} characterId={3} encounterId={1} isCeremonyActive />,
      {
        wrapper,
      }
    );
    await userEvent.click(await screen.findByRole('button', { name: /Edge/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Choose' }));
    await waitFor(() =>
      expect(api.chooseUltimate).toHaveBeenCalledWith({
        character_sheet_id: 3,
        choice_key: 'category:owned:2:sword',
      })
    );
    expect(await screen.findByText('Cinder Crown')).toBeInTheDocument();
  });

  it('renders the deferred-death banner as an alert', async () => {
    vi.mocked(api.getAudereUltimates).mockResolvedValue({
      reveal: null,
      readied: null,
      deferred_death_text: 'PLACEHOLDER death line',
    });
    render(
      <UltimateRevealGate characterSheetId={3} characterId={3} encounterId={1} isCeremonyActive />,
      {
        wrapper,
      }
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('PLACEHOLDER death line');
  });

  it('uses Majora chrome for a Crossing reveal', async () => {
    vi.mocked(api.getAudereUltimates).mockResolvedValue({
      ...OPEN,
      reveal: { ...OPEN.reveal!, ceremony: 'audere_majora' },
    });
    render(
      <UltimateRevealGate characterSheetId={3} characterId={3} encounterId={1} isCeremonyActive />,
      {
        wrapper,
      }
    );
    expect(await screen.findByTestId('ultimate-reveal-dialog')).toHaveClass('border-amber-500/60');
  });
});
