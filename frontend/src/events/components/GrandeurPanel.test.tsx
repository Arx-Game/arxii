/**
 * GrandeurPanel (#2357) — the once-in-a-lifetime event grandeur investment panel.
 *
 * Covers:
 *   1. Renders nothing when contribution is closed and no rows exist.
 *   2. Renders existing contributions + total.
 *   3. Invest dispatches contributeGrandeur with the selected category/amount.
 *   4. A rejected contribution surfaces the server's error message inline.
 *   5. The invest controls are hidden when the event can't take contributions.
 */
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { GrandeurPanel } from './GrandeurPanel';
import type { EventGrandeurContribution } from '../types';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function render(ui: ReactElement, options?: RenderOptions) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

const contributeGrandeurMock = vi.fn();

vi.mock('../queries', () => ({
  contributeGrandeur: (...args: unknown[]) => contributeGrandeurMock(...args),
}));

describe('GrandeurPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    contributeGrandeurMock.mockResolvedValue('Investment recorded.');
  });

  it('renders nothing when contribution is closed and there are no rows', () => {
    const { container } = render(
      <GrandeurPanel
        eventId={1}
        contributions={[]}
        totalSpent={0}
        actorCharacterId={42}
        canContribute={false}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders existing contributions and the formatted total', () => {
    const rows: EventGrandeurContribution[] = [
      {
        id: 1,
        category: 'venue',
        contributed_by: 5,
        contributed_by_name: 'Lucita',
        amount_spent: 1234,
        created_at: '2026-01-01T00:00:00Z',
      },
    ];
    render(
      <GrandeurPanel
        eventId={1}
        contributions={rows}
        totalSpent={1234}
        actorCharacterId={42}
        canContribute={false}
      />
    );
    expect(screen.getByTestId('grandeur-total')).toHaveTextContent('12g 3s 4c');
    expect(screen.getByText(/Lucita/)).toBeInTheDocument();
  });

  it('hides the invest controls when the event cannot take contributions', () => {
    render(
      <GrandeurPanel
        eventId={1}
        contributions={[
          {
            id: 1,
            category: 'venue',
            contributed_by: 5,
            contributed_by_name: 'Lucita',
            amount_spent: 100,
            created_at: '2026-01-01T00:00:00Z',
          },
        ]}
        totalSpent={100}
        actorCharacterId={42}
        canContribute={false}
      />
    );
    expect(screen.queryByTestId('grandeur-contribute-button')).not.toBeInTheDocument();
  });

  it('dispatches contributeGrandeur with the entered category and amount', async () => {
    render(
      <GrandeurPanel
        eventId={7}
        contributions={[]}
        totalSpent={0}
        actorCharacterId={42}
        canContribute
      />
    );

    fireEvent.change(screen.getByTestId('grandeur-amount-input'), { target: { value: '5000' } });
    fireEvent.click(screen.getByTestId('grandeur-contribute-button'));

    await waitFor(() => {
      expect(contributeGrandeurMock).toHaveBeenCalledWith(42, 7, 'venue', 5000);
    });
  });

  it('disables Invest for a non-positive or blank amount', () => {
    render(
      <GrandeurPanel
        eventId={7}
        contributions={[]}
        totalSpent={0}
        actorCharacterId={42}
        canContribute
      />
    );
    expect(screen.getByTestId('grandeur-contribute-button')).toBeDisabled();

    fireEvent.change(screen.getByTestId('grandeur-amount-input'), { target: { value: '0' } });
    expect(screen.getByTestId('grandeur-contribute-button')).toBeDisabled();
  });

  it('surfaces the server error message on a rejected contribution', async () => {
    contributeGrandeurMock.mockRejectedValue(new Error('You cannot afford that much.'));

    render(
      <GrandeurPanel
        eventId={7}
        contributions={[]}
        totalSpent={0}
        actorCharacterId={42}
        canContribute
      />
    );

    fireEvent.change(screen.getByTestId('grandeur-amount-input'), { target: { value: '5000' } });
    fireEvent.click(screen.getByTestId('grandeur-contribute-button'));

    await waitFor(() => {
      expect(screen.getByTestId('grandeur-error')).toHaveTextContent(
        'You cannot afford that much.'
      );
    });
  });
});
