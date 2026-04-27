/**
 * ChatWindow Tests
 *
 * Verifies that narrative messages render with distinct light-red styling
 * while normal and system messages render with standard styling.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ChatWindow } from './ChatWindow';
import { GAME_MESSAGE_TYPE } from '@/hooks/types';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const makeMsg = (
  content: string,
  type: (typeof GAME_MESSAGE_TYPE)[keyof typeof GAME_MESSAGE_TYPE],
  id = 'msg-1'
) => ({
  id,
  content,
  timestamp: Date.now(),
  type,
});

describe('ChatWindow', () => {
  it('renders narrative message with distinct light-red styling', () => {
    const messages = [makeMsg('A vision of the future unfolds...', GAME_MESSAGE_TYPE.NARRATIVE)];
    render(<ChatWindow messages={messages} />, { wrapper: createWrapper() });

    // The narrative wrapper div should have the red border class
    const messageContainer = screen
      .getByText('A vision of the future unfolds...')
      .closest('.border-l-2');
    expect(messageContainer).toBeInTheDocument();
    expect(messageContainer).toHaveClass('border-red-500');
    expect(messageContainer).toHaveClass('bg-red-950/20');
  });

  it('renders normal text messages without narrative styling', () => {
    const messages = [makeMsg('You look around the room.', GAME_MESSAGE_TYPE.TEXT)];
    render(<ChatWindow messages={messages} />, { wrapper: createWrapper() });

    const messageContainer = screen.getByText('You look around the room.').closest('.mb-2');
    expect(messageContainer).not.toHaveClass('border-l-2');
    expect(messageContainer).not.toHaveClass('border-red-500');
  });

  it('renders multiple messages with correct styling for each type', () => {
    const messages = [
      makeMsg('[NARRATIVE] The realm trembles.', GAME_MESSAGE_TYPE.NARRATIVE, 'msg-1'),
      makeMsg('You enter the hall.', GAME_MESSAGE_TYPE.TEXT, 'msg-2'),
      makeMsg('System: Connected.', GAME_MESSAGE_TYPE.SYSTEM, 'msg-3'),
    ];
    render(<ChatWindow messages={messages} />, { wrapper: createWrapper() });

    const narrativeEl = screen.getByText('[NARRATIVE] The realm trembles.').closest('.border-l-2');
    expect(narrativeEl).toBeInTheDocument();
    expect(narrativeEl).toHaveClass('border-red-500');

    const normalEl = screen.getByText('You enter the hall.').closest('.mb-2');
    expect(normalEl).not.toHaveClass('border-red-500');

    const systemEl = screen.getByText('System: Connected.').closest('.mb-2');
    expect(systemEl).not.toHaveClass('border-red-500');
  });

  it('shows empty state when no messages', () => {
    render(<ChatWindow messages={[]} />, { wrapper: createWrapper() });
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });
});
