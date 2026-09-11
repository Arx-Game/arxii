import { useCallback, useEffect, useRef, useState } from 'react';

export interface DraftKey {
  accountId: number;
  personaId: number;
  conversationKey: string;
}

export interface Draft {
  content: string;
  languageId: number | null;
  recipients: string[];
  replyTo: { interactionId: number; timestamp: string } | null;
  companion: boolean;
  attachment: { actionLinkId: number } | null;
  clientRequestId: string | null;
  status: 'clean' | 'pending' | 'rejected' | 'unknown';
  rejectionReason: string | null;
}

const EMPTY_DRAFT: Draft = {
  content: '',
  languageId: null,
  recipients: [],
  replyTo: null,
  companion: false,
  attachment: null,
  clientRequestId: null,
  status: 'clean',
  rejectionReason: null,
};

export function draftStorageKey(key: DraftKey): string {
  return `arx:play-draft:v2:${key.accountId}:${key.personaId}:${key.conversationKey}`;
}

function readStoredDraft(key: DraftKey): Draft {
  try {
    const raw = sessionStorage.getItem(draftStorageKey(key));
    if (!raw) return EMPTY_DRAFT;
    return { ...EMPTY_DRAFT, ...(JSON.parse(raw) as Partial<Draft>) };
  } catch {
    return EMPTY_DRAFT;
  }
}

function persist(key: DraftKey, draft: Draft): void {
  try {
    sessionStorage.setItem(draftStorageKey(key), JSON.stringify(draft));
  } catch {
    // Storage unavailable (private browsing): the caller surfaces the
    // storage-unavailable notice; the draft still works for this tab only.
  }
}

export function useDraftStore(key: DraftKey) {
  const [draft, setDraft] = useState<Draft>(() => readStoredDraft(key));
  const lastSentContentRef = useRef<string | null>(null);
  // `useState(() => readStoredDraft(key))` above only hydrates once, at
  // mount. A caller that keeps one `useDraftStore` instance mounted across a
  // `key` change (e.g. `CommandInput` never remounts when its conversation
  // changes — see its own `previousDraftKey`/re-hydration effect, the exact
  // same problem, in `CommandInput.tsx`) would otherwise keep the OLD
  // conversation's `draft` in memory while `persist()`/`acknowledge()`/etc.
  // write under the NEW key: silently mixing draft state across
  // conversations (#3760 Task 8 review finding, fixed here rather than at
  // every call site). Compares the derived storage-key STRING, not `key`
  // object identity, so a caller re-creating the key object every render
  // (a plain object literal) doesn't spuriously re-hydrate.
  const currentStorageKeyRef = useRef<string>(draftStorageKey(key));
  useEffect(() => {
    const nextStorageKey = draftStorageKey(key);
    if (currentStorageKeyRef.current === nextStorageKey) return;
    currentStorageKeyRef.current = nextStorageKey;
    lastSentContentRef.current = null;
    setDraft(readStoredDraft(key));
  }, [key]);

  const update = useCallback(
    (patch: Partial<Draft>) => {
      setDraft((prev) => {
        const next = { ...prev, ...patch };
        persist(key, next);
        return next;
      });
    },
    [key]
  );

  const setContent = useCallback(
    (content: string) =>
      // Editing invalidates whatever attempt is in flight: the outstanding
      // clientRequestId no longer names the current content, so a stale
      // ack/reject/unknown for it must not touch this newer, unsent edit.
      update({ content, clientRequestId: null, status: 'clean', rejectionReason: null }),
    [update]
  );

  const beginSend = useCallback((): string => {
    // Computed from the current `draft` closure rather than inside a setState
    // updater: React does not guarantee the updater callback runs
    // synchronously, so a value it assigns is not safe to read immediately
    // after calling setDraft (only across a re-render).
    const contentUnchanged = lastSentContentRef.current === draft.content && draft.clientRequestId;
    const id = contentUnchanged ? (draft.clientRequestId as string) : crypto.randomUUID();
    lastSentContentRef.current = draft.content;
    const next: Draft = { ...draft, clientRequestId: id, status: 'pending', rejectionReason: null };
    persist(key, next);
    setDraft(next);
    return id;
  }, [key, draft]);

  const acknowledge = useCallback(
    (clientRequestId: string) => {
      setDraft((prev) => {
        if (prev.clientRequestId !== clientRequestId) return prev; // stale ack, ignore
        persist(key, EMPTY_DRAFT);
        return EMPTY_DRAFT;
      });
    },
    [key]
  );

  const reject = useCallback(
    (clientRequestId: string, reason: string) => {
      setDraft((prev) => {
        if (prev.clientRequestId !== clientRequestId) return prev;
        const next: Draft = { ...prev, status: 'rejected', rejectionReason: reason };
        persist(key, next);
        return next;
      });
    },
    [key]
  );

  const markUnknown = useCallback(
    (clientRequestId: string) => {
      setDraft((prev) => {
        if (prev.clientRequestId !== clientRequestId) return prev;
        const next: Draft = { ...prev, status: 'unknown' };
        persist(key, next);
        return next;
      });
    },
    [key]
  );

  const discard = useCallback(() => {
    persist(key, EMPTY_DRAFT);
    setDraft(EMPTY_DRAFT);
  }, [key]);

  return { draft, setContent, beginSend, acknowledge, reject, markUnknown, discard };
}
