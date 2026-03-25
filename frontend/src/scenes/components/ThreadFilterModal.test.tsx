import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ThreadFilterModal } from './ThreadFilterModal';
import type { Thread } from '../hooks/useThreading';

const THREAD: Thread = {
  key: 'place:5',
  type: 'place',
  label: 'The Balcony',
  participantPersonas: [
    { id: 1, name: 'Alice' },
    { id: 2, name: 'Bob' },
    { id: 3, name: 'Carol' },
  ],
  latestTimestamp: '2026-01-01T00:00:00Z',
  unreadCount: 0,
};

const defaultProps = {
  open: true,
  onClose: vi.fn(),
  thread: THREAD,
  hiddenPersonaIds: new Set<number>(),
  onTogglePersona: vi.fn(),
};

describe('ThreadFilterModal', () => {
  it('shows all participant personas with checkboxes', () => {
    render(<ThreadFilterModal {...defaultProps} />);

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Carol')).toBeInTheDocument();

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3);
  });

  it('all checked by default when hiddenPersonaIds is empty', () => {
    render(<ThreadFilterModal {...defaultProps} />);

    const checkboxes = screen.getAllByRole('checkbox');
    for (const cb of checkboxes) {
      expect(cb).toBeChecked();
    }
  });

  it('unchecked when persona ID is in hiddenPersonaIds', () => {
    render(<ThreadFilterModal {...defaultProps} hiddenPersonaIds={new Set([2])} />);

    const checkboxes = screen.getAllByRole('checkbox');
    // Alice (id 1) checked, Bob (id 2) unchecked, Carol (id 3) checked
    expect(checkboxes[0]).toBeChecked();
    expect(checkboxes[1]).not.toBeChecked();
    expect(checkboxes[2]).toBeChecked();
  });

  it('clicking checkbox calls onTogglePersona', async () => {
    const onTogglePersona = vi.fn();
    const user = userEvent.setup();

    render(<ThreadFilterModal {...defaultProps} onTogglePersona={onTogglePersona} />);

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[1]); // Bob

    expect(onTogglePersona).toHaveBeenCalledWith(2);
  });

  it('displays the thread label in the title', () => {
    render(<ThreadFilterModal {...defaultProps} />);

    expect(screen.getByText('Filter: The Balcony')).toBeInTheDocument();
  });

  it('close button calls onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(<ThreadFilterModal {...defaultProps} onClose={onClose} />);

    const closeButton = screen.getByRole('button', { name: 'Close' });
    await user.click(closeButton);

    expect(onClose).toHaveBeenCalled();
  });
});
