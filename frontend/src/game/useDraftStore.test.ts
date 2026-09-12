import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDraftStore, draftStorageKey } from './useDraftStore';

const key = { accountId: 1, personaId: 7, conversationKey: 'room:42' };

describe('useDraftStore', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('mints a client_request_id on first send and reuses it on retry of the same content', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let firstId = '';
    act(() => {
      firstId = result.current.beginSend();
    });
    expect(result.current.draft.status).toBe('pending');
    let secondId = '';
    act(() => {
      secondId = result.current.beginSend();
    });
    expect(secondId).toBe(firstId);
  });

  // #3784 — the composer is the single source of truth for its own text, so
  // a caller appending to the current draft (`CommandInput`'s @target append)
  // needs an updater form; reading `draft.content` from a render closure
  // instead would append to whatever was current one render ago.
  it('setContent accepts an updater over the current content, and still resets the attempt', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods'));
    let sentId = '';
    act(() => {
      sentId = result.current.beginSend({ command: 'whisper', targets: ['Bob'] });
    });
    expect(result.current.draft.clientRequestId).toBe(sentId);

    act(() => result.current.setContent((previous) => `${previous} at @Bob`));

    expect(result.current.draft.content).toBe('Silas nods at @Bob');
    // An append is an edit like any other: the in-flight attempt and the mode
    // it was composed under are invalidated, not carried over.
    expect(result.current.draft.clientRequestId).toBeNull();
    expect(result.current.draft.status).toBe('clean');
    expect(result.current.draft.mode).toBeNull();
    expect(JSON.parse(sessionStorage.getItem(draftStorageKey(key)) as string).content).toBe(
      'Silas nods at @Bob'
    );
  });

  it('mints a new id after the content changes', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let firstId = '';
    act(() => {
      firstId = result.current.beginSend();
    });
    act(() => result.current.setContent('Silas waves.'));
    let secondId = '';
    act(() => {
      secondId = result.current.beginSend();
    });
    expect(secondId).not.toBe(firstId);
  });

  it('acknowledge clears the draft only when the id matches the current pending attempt', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let pendingId = '';
    act(() => {
      pendingId = result.current.beginSend();
    });
    // A newer edit supersedes the pending attempt before its response arrives.
    act(() => result.current.setContent('Silas nods, then waves.'));
    act(() => result.current.acknowledge(pendingId));
    // The stale ack must NOT clear the newer, unsent edit.
    expect(result.current.draft.content).toBe('Silas nods, then waves.');
  });

  it('scopes storage per accountId/personaId/conversationKey, not a derived string', () => {
    expect(draftStorageKey(key)).toBe('arx:play-draft:v2:1:7:room:42');
    expect(draftStorageKey({ ...key, conversationKey: 'room:43' })).not.toBe(draftStorageKey(key));
  });

  it('acknowledge clears the draft back to empty/clean when the id matches', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let pendingId = '';
    act(() => {
      pendingId = result.current.beginSend();
    });
    act(() => result.current.acknowledge(pendingId));
    expect(result.current.draft.content).toBe('');
    expect(result.current.draft.status).toBe('clean');
    expect(result.current.draft.clientRequestId).toBeNull();
  });

  it('reject marks the draft rejected with a reason when the id matches', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let pendingId = '';
    act(() => {
      pendingId = result.current.beginSend();
    });
    act(() => result.current.reject(pendingId, 'You cannot pose here.'));
    expect(result.current.draft.status).toBe('rejected');
    expect(result.current.draft.rejectionReason).toBe('You cannot pose here.');
    // The rejected content is preserved so the player can revise and resend.
    expect(result.current.draft.content).toBe('Silas nods.');
  });

  it('reject ignores a stale id and leaves the newer, unsent edit untouched', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let pendingId = '';
    act(() => {
      pendingId = result.current.beginSend();
    });
    act(() => result.current.setContent('Silas nods, then waves.'));
    act(() => result.current.reject(pendingId, 'stale rejection'));
    expect(result.current.draft.content).toBe('Silas nods, then waves.');
    expect(result.current.draft.status).toBe('clean');
    expect(result.current.draft.rejectionReason).toBeNull();
  });

  it('markUnknown marks the draft unknown when the id matches', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let pendingId = '';
    act(() => {
      pendingId = result.current.beginSend();
    });
    act(() => result.current.markUnknown(pendingId));
    expect(result.current.draft.status).toBe('unknown');
    expect(result.current.draft.content).toBe('Silas nods.');
  });

  it('reuses the persisted client_request_id on the first beginSend after a fresh mount with an already-pending draft (#3760 Task 11 stranded-draft retry)', () => {
    sessionStorage.setItem(
      draftStorageKey(key),
      JSON.stringify({
        content: 'Silas nods.',
        languageId: null,
        recipients: [],
        replyTo: null,
        companion: false,
        attachment: null,
        clientRequestId: 'stranded-id',
        status: 'pending',
        rejectionReason: null,
        mode: null,
      })
    );
    const { result } = renderHook(() => useDraftStore(key));
    let id = '';
    act(() => {
      id = result.current.beginSend();
    });
    expect(id).toBe('stranded-id');
  });

  it('reuses the persisted client_request_id on the first beginSend after a fresh mount with an already-REJECTED draft (#3760 Task 11 review fix)', () => {
    // The `pending`/`unknown` cases above are not the only ones: a resend of
    // an untouched `rejected` draft after a reload must reuse its id too --
    // this was a real bug in the first version of `initialLastSentContent`,
    // which special-cased only `pending`/`unknown` and missed `rejected`.
    sessionStorage.setItem(
      draftStorageKey(key),
      JSON.stringify({
        content: 'Silas nods.',
        languageId: null,
        recipients: [],
        replyTo: null,
        companion: false,
        attachment: null,
        clientRequestId: 'rejected-id',
        status: 'rejected',
        rejectionReason: 'You cannot pose here.',
        mode: null,
      })
    );
    const { result } = renderHook(() => useDraftStore(key));
    let id = '';
    act(() => {
      id = result.current.beginSend();
    });
    expect(id).toBe('rejected-id');
  });

  describe('mode (#3760 Task 11 critical review fix)', () => {
    it('beginSend captures the live mode fresh when minting a new id', () => {
      const { result } = renderHook(() => useDraftStore(key));
      act(() => result.current.setContent('Silas whispers.'));
      act(() => {
        result.current.beginSend({ command: 'whisper', targets: ['Bob'] });
      });
      expect(result.current.draft.mode).toEqual({ command: 'whisper', targets: ['Bob'] });
    });

    it('beginSend PRESERVES the stored mode when reusing an id (content unchanged), ignoring a different live mode', () => {
      const { result } = renderHook(() => useDraftStore(key));
      act(() => result.current.setContent('Silas whispers.'));
      act(() => {
        result.current.beginSend({ command: 'whisper', targets: ['Bob'] });
      });
      // Retried with a DIFFERENT live mode (e.g. the ModeSelector switched to
      // pose) -- since the content is unchanged, the ORIGINAL mode must win.
      act(() => {
        result.current.beginSend({ command: 'pose', targets: [] });
      });
      expect(result.current.draft.mode).toEqual({ command: 'whisper', targets: ['Bob'] });
    });

    it('a fresh mount with an already-pending draft preserves its stored mode on the first beginSend, ignoring the live mode passed in', () => {
      sessionStorage.setItem(
        draftStorageKey(key),
        JSON.stringify({
          content: 'Silas whispers.',
          languageId: null,
          recipients: [],
          replyTo: null,
          companion: false,
          attachment: null,
          clientRequestId: 'stranded-id',
          status: 'pending',
          rejectionReason: null,
          mode: { command: 'whisper', targets: ['Bob'] },
        })
      );
      const { result } = renderHook(() => useDraftStore(key));
      act(() => {
        // A live mode of 'pose' -- e.g. the tab reopened on the room feed.
        result.current.beginSend({ command: 'pose', targets: [] });
      });
      expect(result.current.draft.mode).toEqual({ command: 'whisper', targets: ['Bob'] });
    });

    it('setContent clears the stored mode, so the NEXT beginSend captures whatever live mode is passed', () => {
      const { result } = renderHook(() => useDraftStore(key));
      act(() => result.current.setContent('Silas whispers.'));
      act(() => {
        result.current.beginSend({ command: 'whisper', targets: ['Bob'] });
      });
      act(() => result.current.setContent('Silas whispers, revised.'));
      expect(result.current.draft.mode).toBeNull();
      act(() => {
        result.current.beginSend({ command: 'say', targets: [] });
      });
      expect(result.current.draft.mode).toEqual({ command: 'say', targets: [] });
    });
  });

  it('mints a fresh id on the first beginSend after a fresh mount when the content has since changed', () => {
    sessionStorage.setItem(
      draftStorageKey(key),
      JSON.stringify({
        content: 'Silas nods.',
        languageId: null,
        recipients: [],
        replyTo: null,
        companion: false,
        attachment: null,
        clientRequestId: 'stranded-id',
        status: 'unknown',
        rejectionReason: null,
      })
    );
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas waves.'));
    let id = '';
    act(() => {
      id = result.current.beginSend();
    });
    expect(id).not.toBe('stranded-id');
  });

  it('markUnknown ignores a stale id and leaves the newer, unsent edit untouched', () => {
    const { result } = renderHook(() => useDraftStore(key));
    act(() => result.current.setContent('Silas nods.'));
    let pendingId = '';
    act(() => {
      pendingId = result.current.beginSend();
    });
    act(() => result.current.setContent('Silas nods, then waves.'));
    act(() => result.current.markUnknown(pendingId));
    expect(result.current.draft.content).toBe('Silas nods, then waves.');
    expect(result.current.draft.status).toBe('clean');
  });

  describe('storageUnavailable (#3760 Task 11)', () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('is false by default when sessionStorage writes succeed', () => {
      const { result } = renderHook(() => useDraftStore(key));
      expect(result.current.storageUnavailable).toBe(false);
      act(() => result.current.setContent('Silas nods.'));
      expect(result.current.storageUnavailable).toBe(false);
    });

    it('becomes true when a sessionStorage write throws (private browsing)', () => {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('QuotaExceededError');
      });
      const { result } = renderHook(() => useDraftStore(key));
      act(() => result.current.setContent('Silas nods.'));
      expect(result.current.storageUnavailable).toBe(true);
      // The draft still works in memory for this tab even though it can't persist.
      expect(result.current.draft.content).toBe('Silas nods.');
    });

    it('becomes true when beginSend cannot persist the pending attempt', () => {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('QuotaExceededError');
      });
      const { result } = renderHook(() => useDraftStore(key));
      act(() => result.current.setContent('Silas nods.'));
      act(() => {
        result.current.beginSend();
      });
      expect(result.current.storageUnavailable).toBe(true);
      expect(result.current.draft.status).toBe('pending');
    });

    it('recovers to false once a write succeeds again', () => {
      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('QuotaExceededError');
      });
      const { result } = renderHook(() => useDraftStore(key));
      act(() => result.current.setContent('Silas nods.'));
      expect(result.current.storageUnavailable).toBe(true);

      setItemSpy.mockRestore();
      act(() => result.current.setContent('Silas nods, then waves.'));
      expect(result.current.storageUnavailable).toBe(false);
    });
  });
});
