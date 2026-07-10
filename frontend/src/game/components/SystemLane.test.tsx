import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SystemLane } from './SystemLane';
import { GAME_MESSAGE_TYPE } from '@/hooks/types';
import type { GameMessage } from '@/hooks/types';

function makeMessage(id: string, content: string): GameMessage & { id: string } {
  return {
    id,
    content,
    timestamp: Date.parse('2026-01-01T00:00:00Z'),
    type: GAME_MESSAGE_TYPE.SYSTEM,
  };
}

describe('SystemLane', () => {
  it('renders nothing when there are no messages', () => {
    const { container } = render(<SystemLane messages={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('starts collapsed, showing a count badge and no message list', () => {
    render(<SystemLane messages={[makeMessage('1', 'Server restarting soon.')]} />);

    expect(screen.getByTestId('system-lane-count')).toHaveTextContent('1');
    expect(screen.queryByTestId('system-lane-messages')).toBeNull();
    expect(screen.queryByText('Server restarting soon.')).not.toBeInTheDocument();
  });

  it('expands to reveal messages on click, and hides the count badge', () => {
    render(<SystemLane messages={[makeMessage('1', 'Server restarting soon.')]} />);

    fireEvent.click(screen.getByRole('button', { name: /system/i }));

    expect(screen.getByTestId('system-lane-messages')).toBeInTheDocument();
    expect(screen.getByText('Server restarting soon.')).toBeInTheDocument();
    expect(screen.queryByTestId('system-lane-count')).toBeNull();
  });

  it('collapses again on a second click', () => {
    render(<SystemLane messages={[makeMessage('1', 'Server restarting soon.')]} />);
    const toggle = screen.getByRole('button', { name: /system/i });

    fireEvent.click(toggle);
    expect(screen.getByTestId('system-lane-messages')).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.queryByTestId('system-lane-messages')).toBeNull();
    expect(screen.getByTestId('system-lane-count')).toHaveTextContent('1');
  });

  it('never applies terminal styling (no bg-black / font-mono) on the lane container', () => {
    const { container } = render(
      <SystemLane messages={[makeMessage('1', 'Server restarting soon.')]} />
    );
    const lane = container.firstElementChild as HTMLElement;
    expect(lane.className).not.toMatch(/bg-black/);
    expect(lane.className).not.toMatch(/font-mono/);
    expect(lane.className).toMatch(/text-xs/);
    expect(lane.className).toMatch(/text-muted-foreground/);
  });
});
