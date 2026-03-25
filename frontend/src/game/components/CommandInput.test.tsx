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

  it('whisper mode uses target=text syntax', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Bob'],
      label: 'Whisper \u2192 Bob',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'whisper Bob=secret message');
  });

  it('prepends targets with @ syntax for non-whisper commands', () => {
    const mode: ComposerMode = {
      command: 'pose',
      targets: ['Bob', 'Carol'],
      label: 'Pose \u2192 Bob, Carol',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'waves hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose @Bob,@Carol waves hello');
  });

  it('appends @name to input when targetToAppend is set', () => {
    const onConsumed = vi.fn();
    const { rerender } = render(
      <CommandInput character="Alice" targetToAppend={null} onTargetConsumed={onConsumed} />
    );

    rerender(<CommandInput character="Alice" targetToAppend="Bob" onTargetConsumed={onConsumed} />);

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
