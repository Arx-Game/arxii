/**
 * ChatWindow Tests
 *
 * Verifies that narrative messages render with distinct light-red styling,
 * gemit messages render with green styling, and normal messages render with
 * standard styling.
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

  it('renders gemit message with distinct green styling', () => {
    const messages = [makeMsg('[GEMIT] The realm shakes!', GAME_MESSAGE_TYPE.GEMIT)];
    render(<ChatWindow messages={messages} />, { wrapper: createWrapper() });

    const messageContainer = screen.getByText('[GEMIT] The realm shakes!').closest('.border-l-2');
    expect(messageContainer).toBeInTheDocument();
    expect(messageContainer).toHaveClass('border-green-500');
    expect(messageContainer).toHaveClass('bg-green-950/20');
  });

  it('renders gemit text in green-300 color class', () => {
    const messages = [makeMsg('[GEMIT] A new era begins.', GAME_MESSAGE_TYPE.GEMIT)];
    render(<ChatWindow messages={messages} />, { wrapper: createWrapper() });

    // The EvenniaMessage span should carry text-green-300
    const textEl = screen.getByText('[GEMIT] A new era begins.');
    expect(textEl).toHaveClass('text-green-300');
  });

  it('renders mixed message types with correct styling for each', () => {
    const messages = [
      makeMsg('[NARRATIVE] The realm trembles.', GAME_MESSAGE_TYPE.NARRATIVE, 'msg-1'),
      makeMsg('[GEMIT] A new era.', GAME_MESSAGE_TYPE.GEMIT, 'msg-2'),
      makeMsg('You enter the hall.', GAME_MESSAGE_TYPE.TEXT, 'msg-3'),
    ];
    render(<ChatWindow messages={messages} />, { wrapper: createWrapper() });

    const narrativeEl = screen.getByText('[NARRATIVE] The realm trembles.').closest('.border-l-2');
    expect(narrativeEl).toHaveClass('border-red-500');
    expect(narrativeEl).not.toHaveClass('border-green-500');

    const gemitEl = screen.getByText('[GEMIT] A new era.').closest('.border-l-2');
    expect(gemitEl).toHaveClass('border-green-500');
    expect(gemitEl).not.toHaveClass('border-red-500');

    const normalEl = screen.getByText('You enter the hall.').closest('.mb-2');
    expect(normalEl).not.toHaveClass('border-l-2');
  });

  it('shows empty state when no messages', () => {
    render(<ChatWindow messages={[]} />, { wrapper: createWrapper() });
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });
});
