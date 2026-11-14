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
const navigate = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}));

import * as magicApi from '@/magic/api';
import * as ritualsApi from '@/rituals/api';
import { throwApiError } from '@/lib/errors';
import { toast } from 'sonner';
import { ThreadResonanceDialog } from '../ThreadResonanceDialog';

const thread = {
  id: 7,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'TRAIT',
  name: 'Oath',
  display_name: 'Oath',
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
  offering_required: true,
  offering_count: 1,
  unavailable_reason: '',
  options: [
    {
      resonance_id: 2,
      resonance_name: 'Lumen',
      affinity_name: 'Celestial',
      conversion_type: null,
      projected_points: 40,
      qualifying: [
        { item_id: 55, name: 'Silver ring', mode: 'keepsake' },
        { item_id: 56, name: 'Lumen candle', mode: 'material' },
      ],
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

const threadWithRows = {
  ...thread,
  resonance: 1,
  developed_points: 40,
  resonances: [
    { resonance_id: 1, resonance_name: 'Bene', amount: 30, leads: true },
    { resonance_id: 4, resonance_name: 'Gale', amount: 10, leads: false },
  ],
} as Thread;

function renderDialog(forThread: Thread = thread) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<ThreadResonanceDialog thread={forThread} open onOpenChange={vi.fn()} />, {
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
    expect(screen.getByText(/Thread: Oath · level 30 · Bene/)).toBeInTheDocument();
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

  it("keeps the retune square visible on the selected pill's fill", async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
    renderDialog();
    const pill = await screen.findByTestId('resonance-option-2');
    const swatch = screen.getByTestId('resonance-swatch-2');
    expect(pill).toHaveClass('bg-primary');
    expect(swatch).not.toHaveClass('bg-primary');
  });

  it('says so when nothing carried pays the offering', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
    renderDialog();
    fireEvent.click(await screen.findByTestId('resonance-option-3'));
    expect(screen.getByTestId('resonance-no-offering')).toHaveTextContent(
      'You carry no offering for Umbra.'
    );
    expect(screen.getByTestId('resonance-retune')).toBeDisabled();
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

  it('opens the thread the result names when it is a different one', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
      makeOptions({ offering_required: false, offering_count: 0 })
    );
    vi.mocked(ritualsApi.performRitual).mockResolvedValue({
      ritual_id: 9,
      execution_kind: 'SERVICE',
      message: 'Moved.',
      result: { thread_id: 12 },
    });
    renderDialog();
    fireEvent.click(await screen.findByTestId('resonance-option-3'));
    fireEvent.click(screen.getByTestId('resonance-retune'));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/threads/12'));
  });

  it('asks for no offering when the rite needs none', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
      makeOptions({ offering_required: false, offering_count: 0 })
    );
    vi.mocked(ritualsApi.performRitual).mockResolvedValue({
      ritual_id: 9,
      execution_kind: 'SERVICE',
      message: 'Retuned.',
      result: { thread_id: 7 },
    });
    renderDialog();
    await screen.findByText('Lumen (same affinity)');
    expect(screen.queryByTestId('resonance-component-55')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('resonance-retune'));
    await waitFor(() =>
      expect(ritualsApi.performRitual).toHaveBeenCalledWith(
        expect.objectContaining({ components: [] })
      )
    );
    expect(navigate).not.toHaveBeenCalled();
  });

  it('takes exactly as many offerings as the rite asks for', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
      makeOptions({ offering_count: 2 })
    );
    vi.mocked(ritualsApi.performRitual).mockResolvedValue({
      ritual_id: 9,
      execution_kind: 'SERVICE',
    });
    renderDialog();
    fireEvent.click(await screen.findByTestId('resonance-component-55'));
    expect(screen.getByTestId('resonance-retune')).toBeDisabled();
    fireEvent.click(screen.getByTestId('resonance-component-56'));
    fireEvent.click(screen.getByTestId('resonance-retune'));
    await waitFor(() =>
      expect(ritualsApi.performRitual).toHaveBeenCalledWith(
        expect.objectContaining({ components: [55, 56] })
      )
    );
  });

  it("shows the server's refusal when the rite is refused", async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
    vi.mocked(ritualsApi.performRitual).mockImplementation(() =>
      throwApiError(
        new Response(JSON.stringify({ detail: 'This thread cannot move to Lumen.' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }),
        'Failed to perform ritual'
      )
    );
    renderDialog();
    fireEvent.click(await screen.findByTestId('resonance-component-55'));
    fireEvent.click(screen.getByTestId('resonance-retune'));
    expect(await screen.findByTestId('resonance-error')).toHaveTextContent(
      'This thread cannot move to Lumen.'
    );
  });

  it('shows why the thread cannot move in place of the options', async () => {
    vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
      makeOptions({
        options: [],
        unavailable_reason: 'This thread has no resonance it can move to.',
      })
    );
    renderDialog();
    expect(await screen.findByTestId('resonance-unavailable')).toHaveTextContent(
      'This thread has no resonance it can move to.'
    );
    expect(screen.queryByText('Change to')).not.toBeInTheDocument();
    expect(screen.getByTestId('resonance-retune')).toBeDisabled();
  });
  describe('rows (#5123)', () => {
    it('asks for the leading row and all of it by default, and names it in the rite', async () => {
      vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
        makeOptions({ offering_required: false, offering_count: 0 })
      );
      vi.mocked(ritualsApi.performRitual).mockResolvedValue({
        ritual_id: 9,
        execution_kind: 'SERVICE',
        message: 'Retuned.',
        result: { thread_id: 7 },
      });
      renderDialog(threadWithRows);
      await screen.findByText('Lumen (same affinity)');
      expect(magicApi.getThreadResonanceOptions).toHaveBeenCalledWith(7, {
        fromResonance: 1,
        amount: null,
      });
      expect(screen.getByTestId('resonance-from-1')).toHaveAttribute('aria-checked', 'true');
      expect(screen.getByTestId('resonance-amount-value')).toHaveTextContent('30');
      fireEvent.click(screen.getByTestId('resonance-retune'));
      await waitFor(() =>
        expect(ritualsApi.performRitual).toHaveBeenCalledWith({
          character_sheet_id: 100,
          ritual_id: 9,
          kwargs: { thread_id: 7, target_resonance: 2, from_resonance: 1 },
          components: [],
        })
      );
    });

    it('moves from another row, and part of it, reading the options for that move', async () => {
      vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(
        makeOptions({ offering_required: false, offering_count: 0 })
      );
      vi.mocked(ritualsApi.performRitual).mockResolvedValue({
        ritual_id: 9,
        execution_kind: 'SERVICE',
        message: 'Retuned.',
        result: { thread_id: 7 },
      });
      renderDialog(threadWithRows);
      await screen.findByText('Lumen (same affinity)');
      fireEvent.click(screen.getByTestId('resonance-from-4'));
      await waitFor(() =>
        expect(magicApi.getThreadResonanceOptions).toHaveBeenLastCalledWith(7, {
          fromResonance: 4,
          amount: null,
        })
      );
      expect(screen.getByTestId('resonance-amount-value')).toHaveTextContent('10');
      fireEvent.click(screen.getByTestId('resonance-amount-down'));
      fireEvent.click(screen.getByTestId('resonance-amount-down'));
      expect(screen.getByTestId('resonance-amount-value')).toHaveTextContent('8');
      await waitFor(() =>
        expect(magicApi.getThreadResonanceOptions).toHaveBeenLastCalledWith(7, {
          fromResonance: 4,
          amount: 8,
        })
      );
      expect(await screen.findByTestId('resonance-projected')).toHaveTextContent('8 points');
      fireEvent.click(screen.getByTestId('resonance-retune'));
      await waitFor(() =>
        expect(ritualsApi.performRitual).toHaveBeenCalledWith(
          expect.objectContaining({
            kwargs: { thread_id: 7, target_resonance: 2, from_resonance: 4, amount: 8 },
          })
        )
      );
    });

    it('gives All back once an amount was chosen', async () => {
      vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
      renderDialog(threadWithRows);
      await screen.findByText('Lumen (same affinity)');
      expect(screen.getByTestId('resonance-amount-all')).toBeDisabled();
      fireEvent.click(screen.getByTestId('resonance-amount-down'));
      expect(screen.getByTestId('resonance-amount-value')).toHaveTextContent('29');
      fireEvent.click(screen.getByTestId('resonance-amount-all'));
      expect(screen.getByTestId('resonance-amount-value')).toHaveTextContent('30');
    });

    it('shows no from-row choice for a thread with one resonance row', async () => {
      vi.mocked(magicApi.getThreadResonanceOptions).mockResolvedValue(makeOptions());
      renderDialog({
        ...threadWithRows,
        resonances: [{ resonance_id: 1, resonance_name: 'Bene', amount: 40, leads: true }],
      } as Thread);
      await screen.findByText('Lumen (same affinity)');
      expect(screen.queryByTestId('resonance-from')).not.toBeInTheDocument();
    });
  });
});
