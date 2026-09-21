import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUnsavedNavigationGuard } from './useUnsavedNavigationGuard';

function Harness({ dirty }: { dirty: boolean }) {
  useUnsavedNavigationGuard(dirty);
  return null;
}

describe('useUnsavedNavigationGuard', () => {
  let originalPushState: typeof history.pushState;

  beforeEach(() => {
    originalPushState = history.pushState;
    vi.spyOn(window, 'confirm').mockReturnValue(false);
  });

  afterEach(() => {
    history.pushState = originalPushState;
    vi.restoreAllMocks();
  });

  it('blocks tab close while a draft is dirty', () => {
    render(<Harness dirty />);
    const event = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    act(() => window.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
  });

  it('guards in-app history navigation and restores the native method on cleanup', () => {
    const { unmount } = render(<Harness dirty />);
    history.pushState({}, '', '/blocked');
    expect(window.location.pathname).not.toBe('/blocked');
    expect(window.confirm).toHaveBeenCalled();
    unmount();
    expect(history.pushState).toBe(originalPushState);
  });
});
