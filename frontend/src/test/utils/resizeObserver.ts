import { vi } from 'vitest';

/**
 * A `ResizeObserver` a test fires by hand. jsdom has no layout, so the no-op
 * polyfill in `setup.ts` never calls back; a test of code that reacts to an
 * element changing size installs this one and calls `resize()` where a browser
 * would have noticed the change.
 */
export interface ResizeObserverStub {
  /** Every element some observer is watching right now. */
  observed: () => Element[];
  /** Call back every observer that is still watching at least one element. */
  resize: () => void;
}

export function stubResizeObserver(): ResizeObserverStub {
  const observers = new Map<ResizeObserverCallback, Set<Element>>();
  class ControlledResizeObserver {
    private readonly targets = new Set<Element>();
    constructor(private readonly callback: ResizeObserverCallback) {
      observers.set(callback, this.targets);
    }
    observe(target: Element): void {
      this.targets.add(target);
    }
    unobserve(target: Element): void {
      this.targets.delete(target);
    }
    disconnect(): void {
      this.targets.clear();
      observers.delete(this.callback);
    }
  }
  vi.stubGlobal('ResizeObserver', ControlledResizeObserver);
  return {
    observed: () => [...observers.values()].flatMap((targets) => [...targets]),
    resize: () => {
      for (const [callback, targets] of observers) {
        if (targets.size > 0) callback([], {} as ResizeObserver);
      }
    },
  };
}
