import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';

const sendMock = vi.fn();

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ send: sendMock }),
}));

describe('CommandInput', () => {
  beforeEach(() => {
    sendMock.mockClear();
  });

  it('renders with mode label when composerMode is provided', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    expect(screen.getByText('Pose \u2192 Room')).toBeInTheDocument();
  });

  it('submits raw text when no composerMode is set', () => {
    render(<CommandInput character="Alice" />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'hello world' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'hello world');
  });

  it('prepends default command when no explicit command typed', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'stretches languidly' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose stretches languidly');
  });

  it('uses explicit command when one is typed', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'say hello everyone' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'say hello everyone');
  });

  it('prepends targets when mode has targets', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Bob', 'Carol'],
      label: 'Whisper \u2192 Bob, Carol',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'whisper @Bob,@Carol secret message');
  });

  it('appends @name to input when pendingTarget is set', () => {
    const onConsumed = vi.fn();
    const { rerender } = render(
      <CommandInput character="Alice" pendingTarget={null} onPendingTargetConsumed={onConsumed} />
    );

    rerender(
      <CommandInput character="Alice" pendingTarget="Bob" onPendingTargetConsumed={onConsumed} />
    );

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.value).toBe('@Bob');
    expect(onConsumed).toHaveBeenCalled();
  });

  it('does not submit empty text', () => {
    render(<CommandInput character="Alice" />);
    const textarea = screen.getByRole('textbox');

    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
  });
});
