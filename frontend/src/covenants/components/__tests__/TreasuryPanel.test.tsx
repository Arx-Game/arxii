/**
 * TreasuryPanel Tests (#2992)
 *
 * Covers:
 *   1. Renders nothing when treasury_balance is null (non-member viewer).
 *   2. Renders the formatted balance for a member.
 *   3. Deposit dispatches useDepositCovenantFunds with the entered amount.
 *   4. Withdraw dispatches useWithdrawCovenantFunds with the entered amount.
 *   5. A rejected withdrawal surfaces the server's error message inline.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { TreasuryPanel } from '../TreasuryPanel';

vi.mock('@/covenants/queries', () => ({
  useDepositCovenantFunds: vi.fn(),
  useWithdrawCovenantFunds: vi.fn(),
}));

import { useDepositCovenantFunds, useWithdrawCovenantFunds } from '@/covenants/queries';

describe('TreasuryPanel', () => {
  const depositMutate = vi.fn();
  const withdrawMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useDepositCovenantFunds).mockReturnValue({
      mutate: depositMutate,
      isPending: false,
    } as never);
    vi.mocked(useWithdrawCovenantFunds).mockReturnValue({
      mutate: withdrawMutate,
      isPending: false,
    } as never);
  });

  it('renders nothing when treasury_balance is null', () => {
    const { container } = render(
      <TreasuryPanel covenantId={7} treasuryBalance={null} actorCharacterId={42} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders the formatted balance for a member', () => {
    render(<TreasuryPanel covenantId={7} treasuryBalance={347} actorCharacterId={42} />);

    expect(screen.getByTestId('treasury-balance')).toHaveTextContent('3g 4s 7c');
  });

  it('dispatches deposit with the entered amount', () => {
    render(<TreasuryPanel covenantId={7} treasuryBalance={100} actorCharacterId={42} />);

    fireEvent.change(screen.getByTestId('treasury-amount-input'), { target: { value: '50' } });
    fireEvent.click(screen.getByTestId('deposit-button'));

    expect(depositMutate).toHaveBeenCalledWith(50, expect.anything());
  });

  it('dispatches withdraw with the entered amount', () => {
    render(<TreasuryPanel covenantId={7} treasuryBalance={100} actorCharacterId={42} />);

    fireEvent.change(screen.getByTestId('treasury-amount-input'), { target: { value: '30' } });
    fireEvent.click(screen.getByTestId('withdraw-button'));

    expect(withdrawMutate).toHaveBeenCalledWith(30, expect.anything());
  });

  it('disables Deposit/Withdraw for a non-positive or blank amount', () => {
    render(<TreasuryPanel covenantId={7} treasuryBalance={100} actorCharacterId={42} />);

    expect(screen.getByTestId('deposit-button')).toBeDisabled();
    expect(screen.getByTestId('withdraw-button')).toBeDisabled();

    fireEvent.change(screen.getByTestId('treasury-amount-input'), { target: { value: '0' } });
    expect(screen.getByTestId('deposit-button')).toBeDisabled();
  });

  it('surfaces the server error message on a rejected withdrawal', () => {
    vi.mocked(useWithdrawCovenantFunds).mockReturnValue({
      mutate: (_amount: number, opts: { onError: (err: Error) => void }) =>
        opts.onError(
          new Error('Your rank does not carry the authority to spend from the covenant treasury.')
        ),
      isPending: false,
    } as never);

    render(<TreasuryPanel covenantId={7} treasuryBalance={100} actorCharacterId={42} />);

    fireEvent.change(screen.getByTestId('treasury-amount-input'), { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('withdraw-button'));

    expect(screen.getByTestId('treasury-error')).toHaveTextContent(
      'Your rank does not carry the authority to spend from the covenant treasury.'
    );
  });
});
