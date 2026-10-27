import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Thread, ThreadResonanceOptions } from '../../../types';

vi.mock('@/magic/api', async (orig) => ({
  ...(await orig<typeof import('@/magic/api')>()),
  getThreadResonanceOptions: vi.fn(),
}));
vi.mock('@/rituals/api', async (orig) => ({
  ...(await orig<typeof import('@/rituals/api')>()),
  performRitual: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import * as magicApi from '@/magic/api';
import * as ritualsApi from '@/rituals/api';
import { toast } from 'sonner';
import { ThreadResonanceDialog } from '../ThreadResonanceDialog';

const thread = {
  id: 7,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'TRAIT',
  name: 'Oath',
  description: '',
  level: 30,
  developed_points: 40,
  level_cap: 10,
  anchor_cap: 30,
  effective_cap: 10,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
} as Thread;

const makeOptions = (overrides: Partial<ThreadResonanceOptions> = {}): ThreadResonanceOptions => ({
  ritual_id: 9,
  options: [
    {
      resonance_id: 2,
      resonance_name: 'Lumen',
      affinity_name: 'Celestial',
      conversion_type: null,
      projected_points: 40,
      qualifying: [{ item_id: 55, name: 'Silver ring', mode: 'keepsake' }],
    },
    {
      resonance_id: 3,
      resonance_name: 'Umbra',
      affinity_name: 'Abyssal',
      conversion_type: 'FALL',
      projected_points: 30,
      qualifying: [],
    },
  ],
  ...overrides,
});

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<ThreadResonanceDialog thread={thread} open onOpenChange={vi.fn()} />, {
    wrapper: Wrapper,
  });
}

describe('ThreadResonanceDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders header, labelled pills and projected points', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
    renderDialog();
    expect(await screen.findByText('Lumen (same affinity)')).toBeInTheDocument();
    expect(screen.getByText('Umbra (Fall)')).toBeInTheDocument();
    expect(screen.getByText(/Thread: Oath · level 3 · Bene/)).toBeInTheDocument();
    expect(screen.getByTestId('resonance-projected')).toHaveTextContent('40 points → 40');
    fireEvent.click(screen.getByTestId('resonance-option-3'));
    expect(screen.getByTestId('resonance-projected')).toHaveTextContent('40 points → 30');
  });

  it('posts the ritual body for the chosen option and component', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
    vi.mocked(ritualsApi.performRitual).mockResolvedValue({
      ritual_id: 9,
      execution_kind: 'SERVICE',
      message: 'Retuned.',
    });
    renderDialog();
    fireEvent.click(await screen.findByTestId('resonance-component-55'));
    fireEvent.click(screen.getByTestId('resonance-retune'));
    await waitFor(() =>
      expect(ritualsApi.performRitual).toHaveBeenCalledWith({
        character_sheet_id: 100,
        ritual_id: 9,
        kwargs: { thread_id: 7, target_resonance: 2 },
        components: [55],
      })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Retuned.'));
  });

  it('disables the button when no ritual is authored', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
      makeOptions({ ritual_id: null })
    );
    renderDialog();
    await screen.findByText('Lumen (same affinity)');
    fireEvent.click(screen.getByTestId('resonance-component-55'));
    expect(screen.getByTestId('resonance-retune')).toBeDisabled();
  });
});
