/**
 * Pray (#4349): at a holy site the dialog takes the action points to spend, and with
 * characters present it can pray for one of them; both ride the `pray` dispatch.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi } from 'vitest';
import { PrayDialog } from '../components/PrayDialog';

const prayMutate = vi.fn();
vi.mock('../queries', () => ({
  usePrayMutation: vi.fn(() => ({ mutate: prayMutate, isPending: false })),
}));
vi.mock('@/character-creation/queries', () => ({
  useWorshippedBeings: vi.fn(() => ({ data: [{ id: 4, name: 'Ombrin' }] })),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('PrayDialog', () => {
  beforeEach(() => prayMutate.mockClear());

  it('sends the action points spent at a holy site', () => {
    render(<PrayDialog characterId={3} defaultBeingId={4} site={{ apLeft: 30, apCap: 30 }} />, {
      wrapper,
    });
    fireEvent.click(screen.getByTestId('pray-button'));
    fireEvent.change(screen.getByLabelText('AP'), { target: { value: '15' } });
    fireEvent.change(screen.getByLabelText('Words'), { target: { value: 'Keep this house.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Pray' }));

    expect(prayMutate).toHaveBeenCalledWith(
      expect.objectContaining({ being: 4, text: 'Keep this house.', ap: 15 }),
      expect.anything()
    );
  });

  it('refuses more action points than are left this week', () => {
    render(<PrayDialog characterId={3} defaultBeingId={4} site={{ apLeft: 10, apCap: 30 }} />, {
      wrapper,
    });
    fireEvent.click(screen.getByTestId('pray-button'));
    fireEvent.change(screen.getByLabelText('AP'), { target: { value: '15' } });
    fireEvent.change(screen.getByLabelText('Words'), { target: { value: 'Keep this house.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Pray' }));

    expect(prayMutate).not.toHaveBeenCalled();
  });

  it('prays for someone present by their persona', () => {
    render(
      <PrayDialog
        characterId={3}
        defaultBeingId={4}
        others={[{ personaId: 77, name: 'Hobb' }]}
        triggerLabel="Pray for someone"
        forRequired
      />,
      { wrapper }
    );
    fireEvent.click(screen.getByRole('button', { name: 'Pray for someone' }));
    fireEvent.change(screen.getByLabelText('Words'), { target: { value: 'Spare him.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Pray' }));

    expect(prayMutate).toHaveBeenCalledWith(
      expect.objectContaining({ being: 4, onBehalfOfPersonaId: 77 }),
      expect.anything()
    );
  });
});
