import { useEffect } from 'react';

const UNSAVED_MESSAGE = 'You have an unsent roleplay draft. Leave this page and discard it?';

/** Protects a live composer from tab close and ordinary in-app link navigation. */
export function useUnsavedNavigationGuard(dirty: boolean): void {
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = UNSAVED_MESSAGE;
    };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return;
    const originalPushState = window.history.pushState;
    window.history.pushState = function guardedPushState(state, title, url) {
      const destination =
        url == null ? window.location.href : new URL(String(url), window.location.href).href;
      if (destination !== window.location.href && !window.confirm(UNSAVED_MESSAGE)) return;
      originalPushState.call(window.history, state, title, url);
    };
    return () => {
      window.history.pushState = originalPushState;
    };
  }, [dirty]);
}
