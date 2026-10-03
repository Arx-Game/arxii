import { createPortal } from 'react-dom';
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
      {/* The avatar's play menu and its dialogs portal out of the line; React
          still bubbles their events through here. */}
      {createPortal(<p data-testid="portaled">A description, in a dialog.</p>, document.body)}
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

  it('a contextmenu with no press behind it (the keyboard) opens the menu under its target', () => {
    render(<Line />);
    const avatar = screen.getByTestId('avatar');
    avatar.getBoundingClientRect = () =>
      ({ left: 12, bottom: 30, top: 10, right: 32, width: 20, height: 20 }) as DOMRect;

    fireEvent.contextMenu(avatar);

    expect(onMenu).toHaveBeenCalledWith(12, 30);
    expect(onFold).not.toHaveBeenCalled();
  });

  it("after a right press the browser's menu is swallowed wherever it lands (Windows fires it on mouse-up)", () => {
    render(<Line />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 2, clientX: 40, clientY: 50 });
    fireEvent.pointerUp(text, { button: 2 });
    // The line has folded; the event lands on the feed under the pointer.
    const landed = fireEvent.contextMenu(document.body);

    expect(landed).toBe(false);
    expect(onMenu).not.toHaveBeenCalled();
  });

  it('a press on a menu or dialog portaled out of the line is not a gesture on the line', () => {
    render(<Line />);
    const portaled = screen.getByTestId('portaled');

    fireEvent.pointerDown(portaled, { button: 2, clientX: 40, clientY: 50 });
    fireEvent.pointerUp(portaled, { button: 2 });
    fireEvent.contextMenu(portaled);
    fireEvent.pointerDown(portaled, { pointerType: 'touch', button: 0 });
    vi.advanceTimersByTime(HOLD_MS);

    expect(onFold).not.toHaveBeenCalled();
    expect(onMenu).not.toHaveBeenCalled();
  });

  it('a touch press holds selection and the callout off the line until it ends', () => {
    render(<Line />);
    const line = screen.getByTestId('line');
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { pointerType: 'touch', button: 0 });
    // jsdom's style object drops the vendor `-webkit-touch-callout`; the
    // standard property is the one it keeps.
    expect(line.style.getPropertyValue('user-select')).toBe('none');
    fireEvent.pointerUp(text, { pointerType: 'touch', button: 0 });
    expect(line.style.getPropertyValue('user-select')).toBe('');
  });

  it('does nothing while disabled (a reference view)', () => {
    render(<Line enabled={false} />);
    const text = screen.getByText('Nyx glances toward the noise.');

    fireEvent.pointerDown(text, { button: 2, clientX: 40, clientY: 50 });
    fireEvent.pointerUp(text, { button: 2 });

    expect(onFold).not.toHaveBeenCalled();
  });
});
