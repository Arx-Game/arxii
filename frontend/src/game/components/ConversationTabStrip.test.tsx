import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationTabStrip } from './ConversationTabStrip';
import type { ConversationTabMeta } from './ConversationTabStrip';

const WHISPER_TAB: ConversationTabMeta = {
  key: 'whisper-1',
  label: 'Whisper: Alise, Ben',
  unreadCount: 0,
};

describe('ConversationTabStrip', () => {
  it('renders nothing when tabs is empty', () => {
    const { container } = render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={0}
        tabs={[]}
        activeKey={null}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders the room anchor tab plus a labeled tab per open conversation', () => {
    render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={0}
        tabs={[WHISPER_TAB]}
        activeKey={null}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByRole('tab', { name: 'Room' })).toBeInTheDocument();
    expect(screen.getByText('Whisper: Alise, Ben')).toBeInTheDocument();
  });

  it('shows a numeric unread badge when unreadCount is greater than zero', () => {
    render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={3}
        tabs={[{ ...WHISPER_TAB, unreadCount: 2 }]}
        activeKey={null}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders no badge when unreadCount is zero', () => {
    render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={0}
        tabs={[WHISPER_TAB]}
        activeKey={null}
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('calls onSelect with the tab key when a conversation tab is clicked', () => {
    const onSelect = vi.fn();
    render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={0}
        tabs={[WHISPER_TAB]}
        activeKey={null}
        onSelect={onSelect}
        onClose={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('tab', { name: /Whisper: Alise, Ben/ }));

    expect(onSelect).toHaveBeenCalledWith('whisper-1');
  });

  it('calls onSelect with null when the room anchor tab is clicked', () => {
    const onSelect = vi.fn();
    render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={0}
        tabs={[WHISPER_TAB]}
        activeKey="whisper-1"
        onSelect={onSelect}
        onClose={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('tab', { name: 'Room' }));

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('calls onClose (not onSelect) when the close button is clicked', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(
      <ConversationTabStrip
        roomLabel="Room"
        roomUnreadCount={0}
        tabs={[WHISPER_TAB]}
        activeKey={null}
        onSelect={onSelect}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close Whisper: Alise, Ben' }));

    expect(onClose).toHaveBeenCalledWith('whisper-1');
    expect(onSelect).not.toHaveBeenCalled();
  });
});
