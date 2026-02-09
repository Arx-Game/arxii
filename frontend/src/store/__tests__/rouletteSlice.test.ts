import { describe, it, expect } from 'vitest';
import { rouletteSlice, enqueueRoulette, dismissRoulette, requestSkip } from '../rouletteSlice';
import type { RoulettePayload } from '@/components/roulette/types';

const reducer = rouletteSlice.reducer;

const createPayload = (name: string = 'Test Attack'): RoulettePayload => ({
  template_name: name,
  consequences: [
    { label: 'You miss', tier_name: 'Failure', weight: 3, is_selected: false },
    { label: 'You strike true', tier_name: 'Success', weight: 2, is_selected: true },
  ],
});

describe('rouletteSlice', () => {
  describe('initial state', () => {
    it('starts with no active roulette', () => {
      const state = reducer(undefined, { type: 'unknown' });

      expect(state.current).toBeNull();
      expect(state.queue).toEqual([]);
      expect(state.skipRequested).toBe(false);
    });
  });

  describe('enqueueRoulette', () => {
    it('sets current when nothing is active', () => {
      const payload = createPayload();

      const state = reducer(undefined, enqueueRoulette(payload));

      expect(state.current).toEqual(payload);
      expect(state.queue).toEqual([]);
    });

    it('queues when another roulette is active', () => {
      const first = createPayload('First');
      const second = createPayload('Second');
      const stateAfterFirst = reducer(undefined, enqueueRoulette(first));

      const state = reducer(stateAfterFirst, enqueueRoulette(second));

      expect(state.current).toEqual(first);
      expect(state.queue).toEqual([second]);
    });

    it('queues multiple payloads in order', () => {
      let state = reducer(undefined, enqueueRoulette(createPayload('First')));
      state = reducer(state, enqueueRoulette(createPayload('Second')));
      state = reducer(state, enqueueRoulette(createPayload('Third')));

      expect(state.queue).toHaveLength(2);
      expect(state.queue[0].template_name).toBe('Second');
      expect(state.queue[1].template_name).toBe('Third');
    });
  });

  describe('dismissRoulette', () => {
    it('clears current when queue is empty', () => {
      const state = reducer(undefined, enqueueRoulette(createPayload()));

      const dismissed = reducer(state, dismissRoulette());

      expect(dismissed.current).toBeNull();
      expect(dismissed.queue).toEqual([]);
    });

    it('promotes next queued item to current', () => {
      let state = reducer(undefined, enqueueRoulette(createPayload('First')));
      state = reducer(state, enqueueRoulette(createPayload('Second')));
      state = reducer(state, enqueueRoulette(createPayload('Third')));

      const dismissed = reducer(state, dismissRoulette());

      expect(dismissed.current?.template_name).toBe('Second');
      expect(dismissed.queue).toHaveLength(1);
      expect(dismissed.queue[0].template_name).toBe('Third');
    });

    it('resets skipRequested on dismiss', () => {
      let state = reducer(undefined, enqueueRoulette(createPayload()));
      state = reducer(state, requestSkip());
      expect(state.skipRequested).toBe(true);

      const dismissed = reducer(state, dismissRoulette());

      expect(dismissed.skipRequested).toBe(false);
    });

    it('does nothing when no current', () => {
      const state = reducer(undefined, dismissRoulette());

      expect(state.current).toBeNull();
      expect(state.queue).toEqual([]);
    });
  });

  describe('requestSkip', () => {
    it('sets skipRequested to true', () => {
      const state = reducer(undefined, enqueueRoulette(createPayload()));

      const skipped = reducer(state, requestSkip());

      expect(skipped.skipRequested).toBe(true);
    });
  });
});
