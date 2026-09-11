import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
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
});
