import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HOLD_MS, useLineGestures } from './useLineGestures';

function Line({ enabled = true }: { enabled?: boolean }) {
  const gestures = useLineGestures({ enabled, onFold, onMenu });
  return (
    <div data-testid="line" {...gestures}>
      <span data-testid="avatar" data-pose-avatar>
        N
      </span>
      <p>Nyx glances toward the noise.</p>
    </div>
  );
}

const onFold = vi.fn();
const onMenu = vi.fn();

describe('useLineGestures (#4128)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    onFold.mockReset();
    onMenu.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('a quick right-click on the text folds', () => {
    render(<Line />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 2, clientX: 40, clientY: 50 });
    vi.advanceTimersByTime(HOLD_MS - 50);
    fireEvent.pointerUp(text, { button: 2 });

    expect(onFold).toHaveBeenCalledTimes(1);
    expect(onMenu).not.toHaveBeenCalled();
  });

  it('a held right-click on the text opens the menu where the pointer is, and does not fold', () => {
    render(<Line />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 2, clientX: 40, clientY: 50 });
    vi.advanceTimersByTime(HOLD_MS);
    expect(onMenu).toHaveBeenCalledWith(40, 50);
    fireEvent.pointerUp(text, { button: 2 });

    expect(onFold).not.toHaveBeenCalled();
  });

  it('a right-click on the avatar opens the menu at once', () => {
    render(<Line />);

    fireEvent.pointerDown(screen.getByTestId('avatar'), { button: 2, clientX: 8, clientY: 9 });
    expect(onMenu).toHaveBeenCalledWith(8, 9);
    fireEvent.pointerUp(screen.getByTestId('avatar'), { button: 2 });

    expect(onFold).not.toHaveBeenCalled();
  });

  it('a long-press on the text opens the menu; a tap does nothing', () => {
    render(<Line />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 0, pointerType: 'touch', clientX: 40, clientY: 50 });
    vi.advanceTimersByTime(HOLD_MS - 50);
    fireEvent.pointerUp(text, { button: 0, pointerType: 'touch' });
    expect(onMenu).not.toHaveBeenCalled();
    expect(onFold).not.toHaveBeenCalled();

    fireEvent.pointerDown(text, { button: 0, pointerType: 'touch', clientX: 40, clientY: 50 });
    vi.advanceTimersByTime(HOLD_MS);
    expect(onMenu).toHaveBeenCalledWith(40, 50);
  });

  it('a press that scrolls away is cancelled, not folded', () => {
    render(<Line />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 2, clientX: 40, clientY: 50 });
    fireEvent.pointerCancel(text);
    vi.advanceTimersByTime(HOLD_MS);
    fireEvent.pointerUp(text, { button: 2 });

    expect(onFold).not.toHaveBeenCalled();
    expect(onMenu).not.toHaveBeenCalled();
  });

  it('the left button is left alone', () => {
    render(<Line />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 0, clientX: 40, clientY: 50 });
    vi.advanceTimersByTime(HOLD_MS);
    fireEvent.pointerUp(text, { button: 0 });

    expect(onFold).not.toHaveBeenCalled();
    expect(onMenu).not.toHaveBeenCalled();
  });

  it("the browser's own context menu is suppressed on the line", () => {
    render(<Line />);
    const event = fireEvent.contextMenu(screen.getByText('Nyx glances toward the noise.'));
    expect(event).toBe(false);
  });

  it('does nothing while disabled (a reference view)', () => {
    render(<Line enabled={false} />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 2, clientX: 40, clientY: 50 });
    fireEvent.pointerUp(text, { button: 2 });

    expect(onFold).not.toHaveBeenCalled();
  });
});
