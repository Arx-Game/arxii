/** BeatCard renders the "because" reasons a character-gated option carries. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import type { BeatView } from '../types';

function beatWith(reasons: string[]): BeatView {
  return {
    instance_id: 7,
    template_name: 'PLACEHOLDER mission',
    node_key: 'entry',
    flavor_text: 'PLACEHOLDER the gate.',
    options: [
      {
        option_id: 31,
        approach_id: null,
        label: 'PLACEHOLDER speak the old words',
        kind: 'branch',
        check_type_name: null,
        base_risk: 0,
        reasons,
      },
    ],
    is_paused: false,
    track: null,
  };
}

const useBeatMock = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useBeat: (...args: unknown[]) => useBeatMock(...args),
    useResolveBeat: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  };
});

import { BeatCard } from '../components/BeatCard';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('BeatCard because reasons', () => {
  it('shows each reason under the option label', () => {
    useBeatMock.mockReturnValue({
      data: beatWith(['you are PLACEHOLDER Folk', 'you have PLACEHOLDER Mark']),
      isLoading: false,
    });
    render(withProviders(<BeatCard instanceId={7} roomKey="Gate" />));

    const reasons = screen.getAllByTestId('option-reason');
    expect(reasons.map((r) => r.textContent)).toEqual([
      'because you are PLACEHOLDER Folk',
      'because you have PLACEHOLDER Mark',
    ]);
  });

  it('shows no reason line for an ungated option', () => {
    useBeatMock.mockReturnValue({ data: beatWith([]), isLoading: false });
    render(withProviders(<BeatCard instanceId={7} roomKey="Gate" />));

    expect(screen.queryByTestId('option-reason')).not.toBeInTheDocument();
  });
});
