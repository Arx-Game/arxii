import { describe, it, expect } from 'vitest';
import { deepLinkModalSlice, openDeepLink, closeDeepLink } from '../deepLinkModalSlice';
import type { DeepLinkTarget } from '../deepLinkModalSlice';

const reducer = deepLinkModalSlice.reducer;

describe('deepLinkModalSlice', () => {
  describe('initial state', () => {
    it('starts with no open deep-link modal', () => {
      const state = reducer(undefined, { type: 'unknown' });

      expect(state.current).toBeNull();
    });
  });

  describe('openDeepLink', () => {
    it('sets current to the dispatched target', () => {
      const target: DeepLinkTarget = { modal: 'condition', id: 7 };

      const state = reducer(undefined, openDeepLink(target));

      expect(state.current).toEqual({ modal: 'condition', id: 7 });
    });

    it('replaces an existing target', () => {
      let state = reducer(undefined, openDeepLink({ modal: 'condition', id: 7 }));
      state = reducer(state, openDeepLink({ modal: 'clash', id: 42 }));

      expect(state.current).toEqual({ modal: 'clash', id: 42 });
    });
  });

  describe('closeDeepLink', () => {
    it('resets current back to null', () => {
      const state = reducer(undefined, openDeepLink({ modal: 'condition', id: 7 }));

      const closed = reducer(state, closeDeepLink());

      expect(closed.current).toBeNull();
    });
  });
});
