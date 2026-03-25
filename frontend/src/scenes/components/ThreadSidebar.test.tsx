import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ThreadSidebar } from './ThreadSidebar';
import type { Thread } from '../hooks/useThreading';

function makeThread(overrides: Partial<Thread> = {}): Thread {
  return {
    key: 'room',
    type: 'room',
    label: 'Grand Hall',
    participantPersonas: [{ id: 1, name: 'Alice' }],
    latestTimestamp: '2026-01-01T00:00:00Z',
    unreadCount: 0,
    ...overrides,
  };
}

const defaultProps = {
  threads: [makeThread()],
  activeThreadKey: 'room',
  visibleThreadKeys: new Set<string>(),
  showingAll: true,
  onToggleThread: vi.fn(),
  onSelectThread: vi.fn(),
  onShowAll: vi.fn(),
  onOpenFilter: vi.fn(),
};

describe('ThreadSidebar', () => {
  it('renders "All" button', () => {
    render(<ThreadSidebar {...defaultProps} />);
    expect(screen.getByText('All')).toBeInTheDocument();
  });

  it('renders thread bookmarks with correct labels', () => {
    const threads = [
      makeThread({ key: 'room', label: 'Grand Hall' }),
      makeThread({ key: 'place:5', type: 'place', label: 'Balcony' }),
    ];
    render(<ThreadSidebar {...defaultProps} threads={threads} />);
    expect(screen.getByText('Grand Hall')).toBeInTheDocument();
    expect(screen.getByText('Balcony')).toBeInTheDocument();
  });

  it('"All" button highlighted when showingAll', () => {
    render(<ThreadSidebar {...defaultProps} showingAll={true} />);
    const allButton = screen.getByText('All');
    expect(allButton.className).toContain('bg-accent');
  });

  it('"All" button not highlighted when not showingAll', () => {
    render(<ThreadSidebar {...defaultProps} showingAll={false} />);
    const allButton = screen.getByText('All');
    expect(allButton.className).not.toContain('bg-accent');
  });

  it('click calls both onSelectThread and onToggleThread', async () => {
    const onSelectThread = vi.fn();
    const onToggleThread = vi.fn();
    const user = userEvent.setup();

    render(
      <ThreadSidebar
        {...defaultProps}
        onSelectThread={onSelectThread}
        onToggleThread={onToggleThread}
      />
    );

    await user.click(screen.getByText('Grand Hall'));

    expect(onSelectThread).toHaveBeenCalledWith('room');
    expect(onToggleThread).toHaveBeenCalledWith('room');
  });

  it('right-click calls onOpenFilter', async () => {
    const onOpenFilter = vi.fn();
    const user = userEvent.setup();

    render(<ThreadSidebar {...defaultProps} onOpenFilter={onOpenFilter} />);

    await user.pointer({ keys: '[MouseRight]', target: screen.getByText('Grand Hall') });

    expect(onOpenFilter).toHaveBeenCalledWith('room');
  });

  it('long name lists truncated with title tooltip', () => {
    const thread = makeThread({
      key: 'target:1,2,3,4',
      type: 'target',
      label: 'A, B, C...',
      participantPersonas: [
        { id: 1, name: 'Alice' },
        { id: 2, name: 'Bob' },
        { id: 3, name: 'Carol' },
        { id: 4, name: 'Dave' },
      ],
    });

    render(<ThreadSidebar {...defaultProps} threads={[thread]} />);

    const button = screen.getByText('A, B, C...');
    expect(button.closest('button')?.title).toBe('Alice, Bob, Carol, Dave');
  });

  it('clicking "All" calls onShowAll', async () => {
    const onShowAll = vi.fn();
    const user = userEvent.setup();

    render(<ThreadSidebar {...defaultProps} onShowAll={onShowAll} />);

    await user.click(screen.getByText('All'));
    expect(onShowAll).toHaveBeenCalled();
  });
});
