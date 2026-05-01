/**
 * UndressButton component tests.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { UndressButton } from '../UndressButton';

describe('UndressButton', () => {
  it('renders nothing when no items are equipped', () => {
    const { container } = render(<UndressButton equippedCount={0} onUndress={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders an Undress button when at least one item is equipped', () => {
    render(<UndressButton equippedCount={1} onUndress={vi.fn()} />);
    expect(screen.getByRole('button', { name: /undress/i })).toBeInTheDocument();
  });

  it('fires onUndress immediately when 1 item is worn (no confirm)', async () => {
    const user = userEvent.setup();
    const onUndress = vi.fn();
    render(<UndressButton equippedCount={1} onUndress={onUndress} />);
    await user.click(screen.getByRole('button', { name: /undress/i }));
    expect(onUndress).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('fires onUndress immediately when 2 items are worn (no confirm)', async () => {
    const user = userEvent.setup();
    const onUndress = vi.fn();
    render(<UndressButton equippedCount={2} onUndress={onUndress} />);
    await user.click(screen.getByRole('button', { name: /undress/i }));
    expect(onUndress).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('opens a confirmation dialog when 3+ items are worn', async () => {
    const user = userEvent.setup();
    const onUndress = vi.fn();
    render(<UndressButton equippedCount={3} onUndress={onUndress} />);
    await user.click(screen.getByRole('button', { name: /undress/i }));
    // Confirmation should be visible and onUndress should NOT have fired yet.
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/remove all items/i)).toBeInTheDocument();
    expect(screen.getByText(/wearing 3 items/i)).toBeInTheDocument();
    expect(onUndress).not.toHaveBeenCalled();
  });

  it('fires onUndress after confirming the 3+ dialog', async () => {
    const user = userEvent.setup();
    const onUndress = vi.fn();
    render(<UndressButton equippedCount={4} onUndress={onUndress} />);
    await user.click(screen.getByRole('button', { name: /undress/i }));
    await user.click(await screen.findByRole('button', { name: /remove all/i }));
    expect(onUndress).toHaveBeenCalledTimes(1);
  });

  it('does not fire onUndress when the 3+ dialog is cancelled', async () => {
    const user = userEvent.setup();
    const onUndress = vi.fn();
    render(<UndressButton equippedCount={5} onUndress={onUndress} />);
    await user.click(screen.getByRole('button', { name: /undress/i }));
    await user.click(await screen.findByRole('button', { name: /cancel/i }));
    expect(onUndress).not.toHaveBeenCalled();
  });

  it('honors the disabled prop on the trigger button', () => {
    render(<UndressButton equippedCount={1} onUndress={vi.fn()} disabled />);
    expect(screen.getByRole('button', { name: /undress/i })).toBeDisabled();
  });
});
