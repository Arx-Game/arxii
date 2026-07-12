/**
 * Tests for handleInteractionPayload's background-whisper attention toast
 * (#2166 Task 3). The scene-interaction dispatch itself is covered
 * incidentally; the focus here is the toast-fire/dedupe/own-persona/click
 * behavior layered on top.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const { toastMock, getStateMock, getQueryDataMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  getStateMock: vi.fn(),
  getQueryDataMock: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: Object.assign(toastMock, { error: vi.fn(), success: vi.fn() }),
}));

vi.mock('@/store/store', () => ({
  store: { getState: getStateMock },
}));

vi.mock('@/queryClient', () => ({
  queryClient: { getQueryData: getQueryDataMock },
}));

import { handleInteractionPayload } from '../handleInteractionPayload';
import { addSceneInteraction, openThreadTab, setActiveSession } from '@/store/gameSlice';
import type { InteractionWsPayload } from '../types';
import type { MyRosterEntry } from '@/roster/types';
import type { NavigateFunction } from 'react-router-dom';

function makeRosterEntries(): MyRosterEntry[] {
  return [
    {
      id: 1,
      name: 'Alice',
      character_id: 101,
      profile_picture_url: null,
      primary_persona_id: 11,
      active_persona_id: 11,
    },
    {
      id: 2,
      name: 'Bob',
      character_id: 102,
      profile_picture_url: null,
      primary_persona_id: 22,
      active_persona_id: 22,
    },
  ];
}

function makeWhisperPayload(overrides: Partial<InteractionWsPayload> = {}): InteractionWsPayload {
  return {
    id: 500,
    persona: { id: 11, name: 'Alice-Persona', thumbnail_url: '' },
    content: 'psst',
    mode: 'whisper',
    timestamp: '2026-07-12T00:00:00Z',
    scene_id: 9,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [22],
    target_persona_ids: [],
    ...overrides,
  };
}

describe('handleInteractionPayload', () => {
  let dispatch: ReturnType<typeof vi.fn>;
  let navigate: NavigateFunction;

  beforeEach(() => {
    vi.clearAllMocks();
    dispatch = vi.fn();
    navigate = vi.fn() as unknown as NavigateFunction;
    getStateMock.mockReturnValue({ game: { active: 'Alice' } });
    getQueryDataMock.mockReturnValue(makeRosterEntries());
  });

  it('always dispatches addSceneInteraction regardless of toast outcome', () => {
    const payload = makeWhisperPayload({ id: 490 });
    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(dispatch).toHaveBeenCalledWith(
      addSceneInteraction({ character: 'Bob', interaction: payload })
    );
  });

  it('fires a toast for a whisper delivered to a background session', () => {
    const payload = makeWhisperPayload({ id: 491 });
    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(toastMock).toHaveBeenCalledTimes(1);
    expect(toastMock).toHaveBeenCalledWith(
      'Whisper to Bob from Alice-Persona',
      expect.objectContaining({ action: expect.objectContaining({ label: 'Switch' }) })
    );
  });

  it('dedupes on a repeat interaction id', () => {
    const payload = makeWhisperPayload({ id: 492 });
    handleInteractionPayload('Bob', payload, dispatch, navigate);
    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(toastMock).toHaveBeenCalledTimes(1);
  });

  it('does not toast when the receiving session is the active session', () => {
    getStateMock.mockReturnValue({ game: { active: 'Bob' } });
    const payload = makeWhisperPayload({ id: 502 });

    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(toastMock).not.toHaveBeenCalled();
  });

  it('does not toast for a non-whisper interaction', () => {
    const payload = makeWhisperPayload({ id: 503, mode: 'pose' });

    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(toastMock).not.toHaveBeenCalled();
  });

  it('does not toast a whisper echoed back to its own author session', () => {
    // Bob's own persona (22) whispering out — Bob's own socket sees the echo.
    const payload = makeWhisperPayload({
      id: 504,
      persona: { id: 22, name: 'Bob-Persona', thumbnail_url: '' },
      receiver_persona_ids: [11],
    });

    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(toastMock).not.toHaveBeenCalled();
  });

  it('still toasts when the roster cache has not resolved own-persona (MVP fallback)', () => {
    getQueryDataMock.mockReturnValue(undefined);
    const payload = makeWhisperPayload({ id: 505 });

    handleInteractionPayload('Bob', payload, dispatch, navigate);

    expect(toastMock).toHaveBeenCalledTimes(1);
  });

  it('click dispatches setActiveSession + openThreadTab and navigates to /game', () => {
    const payload = makeWhisperPayload({ id: 506 });
    handleInteractionPayload('Bob', payload, dispatch, navigate);

    const [, options] = toastMock.mock.calls[0];
    options.action.onClick();

    expect(dispatch).toHaveBeenCalledWith(setActiveSession('Bob'));
    expect(dispatch).toHaveBeenCalledWith(
      openThreadTab({ character: 'Bob', threadKey: 'whisper:11,22' })
    );
    expect(navigate).toHaveBeenCalledWith('/game');
  });

  it('click does not navigate again when already on /game', () => {
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, pathname: '/game' },
    });

    const payload = makeWhisperPayload({ id: 507 });
    handleInteractionPayload('Bob', payload, dispatch, navigate);

    const [, options] = toastMock.mock.calls[0];
    options.action.onClick();

    expect(navigate).not.toHaveBeenCalled();

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });
});
