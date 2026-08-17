/**
 * TradePanel Tests (#2990)
 *
 * Covers:
 *   1. Renders nothing while the session hasn't loaded.
 *   2. Proposed + viewer is the invited party -> shows Accept.
 *   3. Active -> renders both sides' stakes/coin/confirm state, my side first.
 *   4. Confirm dispatches useConfirmTrade.
 *   5. Staging an inventory item dispatches useStageTradeItem with its game_object id.
 *   6. A rejected mutation surfaces the server's error message inline.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { TradePanel } from '../TradePanel';
import type { TradeSession } from '../../api';

vi.mock('../../queries', () => ({
  useTradeSession: vi.fn(),
  useAcceptTrade: vi.fn(),
  useStageTradeItem: vi.fn(),
  useUnstageTradeItem: vi.fn(),
  useSetTradeCoin: vi.fn(),
  useConfirmTrade: vi.fn(),
  useCancelTrade: vi.fn(),
}));

vi.mock('@/inventory/hooks/useInventory', () => ({
  useInventory: vi.fn(() => ({ data: [] })),
}));

import {
  useAcceptTrade,
  useCancelTrade,
  useConfirmTrade,
  useSetTradeCoin,
  useStageTradeItem,
  useTradeSession,
  useUnstageTradeItem,
} from '../../queries';
import { useInventory } from '@/inventory/hooks/useInventory';

function idleMutation(overrides: Record<string, unknown> = {}) {
  return { mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: false, ...overrides };
}

function baseSession(overrides: Partial<TradeSession> = {}): TradeSession {
  return {
    id: 1,
    initiator_sheet: 100,
    initiator_name: 'Alice',
    counterparty_sheet: 200,
    counterparty_name: 'Bob',
    status: 'active',
    initiator_confirmed: false,
    counterparty_confirmed: false,
    initiator_coppers: 0,
    counterparty_coppers: 0,
    item_stakes: [],
    created_at: '2026-08-15T00:00:00Z',
    resolved_at: null,
    ...overrides,
  };
}

describe('TradePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAcceptTrade).mockReturnValue(idleMutation() as never);
    vi.mocked(useStageTradeItem).mockReturnValue(idleMutation() as never);
    vi.mocked(useUnstageTradeItem).mockReturnValue(idleMutation() as never);
    vi.mocked(useSetTradeCoin).mockReturnValue(idleMutation() as never);
    vi.mocked(useConfirmTrade).mockReturnValue(idleMutation() as never);
    vi.mocked(useCancelTrade).mockReturnValue(idleMutation() as never);
    vi.mocked(useInventory).mockReturnValue({ data: [] } as never);
  });

  it('renders nothing while the session has not loaded', () => {
    vi.mocked(useTradeSession).mockReturnValue({ data: undefined } as never);
    const { container } = render(<TradePanel sessionId={1} actorCharacterId={200} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows Accept for the invited party on a proposed trade', () => {
    vi.mocked(useTradeSession).mockReturnValue({
      data: baseSession({ status: 'proposed' }),
    } as never);

    // actorCharacterId=200 == counterparty_sheet -> the invited party.
    render(<TradePanel sessionId={1} actorCharacterId={200} />);
    expect(screen.getByTestId('accept-trade-button')).toBeInTheDocument();
  });

  it('renders both sides for an active trade', () => {
    vi.mocked(useTradeSession).mockReturnValue({
      data: baseSession({
        initiator_coppers: 30,
        counterparty_coppers: 10,
        counterparty_confirmed: true,
        item_stakes: [
          {
            id: 1,
            item_instance: 5,
            item_name: 'A Sword',
            offered_by_sheet: 100,
            offered_by_name: 'Alice',
            staked_at: '2026-08-15T00:00:00Z',
          },
        ],
      }),
    } as never);

    // Viewer is the initiator (sheet 100).
    render(<TradePanel sessionId={1} actorCharacterId={100} />);

    expect(screen.getByTestId('trade-side-Your Offer')).toHaveTextContent('A Sword');
    expect(screen.getByTestId('trade-side-Your Offer')).toHaveTextContent('3s');
    expect(screen.getByTestId('trade-side-Their Offer')).toHaveTextContent('1s');
    expect(screen.getByTestId('trade-confirmed-Their Offer')).toHaveTextContent('Confirmed');
  });

  it('dispatches confirm on click', () => {
    const confirmMutation = idleMutation();
    vi.mocked(useConfirmTrade).mockReturnValue(confirmMutation as never);
    vi.mocked(useTradeSession).mockReturnValue({ data: baseSession() } as never);

    render(<TradePanel sessionId={1} actorCharacterId={100} />);
    fireEvent.click(screen.getByTestId('confirm-trade-button'));

    expect(confirmMutation.mutateAsync).toHaveBeenCalled();
  });

  it('stages an inventory item by its game_object id', () => {
    const stageMutation = idleMutation();
    vi.mocked(useStageTradeItem).mockReturnValue(stageMutation as never);
    vi.mocked(useInventory).mockReturnValue({
      data: [
        {
          id: 9,
          game_object_id: 555,
          display_name: 'A Ring',
        },
      ],
    } as never);
    vi.mocked(useTradeSession).mockReturnValue({ data: baseSession() } as never);

    render(<TradePanel sessionId={1} actorCharacterId={100} />);
    fireEvent.click(screen.getByTestId('stage-item-9'));

    expect(stageMutation.mutateAsync).toHaveBeenCalledWith(555);
  });

  it('surfaces a rejected mutation error inline', async () => {
    vi.mocked(useConfirmTrade).mockReturnValue(
      idleMutation({
        mutateAsync: vi.fn().mockRejectedValue(new Error('Adjacency lost.')),
      }) as never
    );
    vi.mocked(useTradeSession).mockReturnValue({ data: baseSession() } as never);

    render(<TradePanel sessionId={1} actorCharacterId={100} />);
    fireEvent.click(screen.getByTestId('confirm-trade-button'));

    expect(await screen.findByTestId('trade-error')).toHaveTextContent('Adjacency lost.');
  });
});
