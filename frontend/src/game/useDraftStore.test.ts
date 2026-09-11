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
      })
    );
    const { result } = renderHook(() => useDraftStore(key));
    let id = '';
    act(() => {
      id = result.current.beginSend();
    });
    expect(id).toBe('stranded-id');
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
