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

/**
 * Returns whether the write actually landed. `useDraftStore` threads the
 * failure case into its `storageUnavailable` field (#3760 Task 11) so the
 * composer can surface "Draft kept in this tab only" instead of silently
 * pretending the draft is durable — it works for this tab only either way,
 * but the player should be told.
 */
function persist(key: DraftKey, draft: Draft): boolean {
  try {
    sessionStorage.setItem(draftStorageKey(key), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

/**
 * `beginSend()`'s "same content as last time -> reuse the id" check compares
 * against `lastSentContentRef`, an in-memory ref that starts life empty on
 * every mount. For a draft hydrated from storage already `pending`/`unknown`
 * (a stranded draft from a reload, #3760 Task 11's Retry/"Resume & retry"),
 * that would otherwise mint a FRESH id on the first `beginSend()` after
 * reload even though the content is unchanged from the original attempt --
 * defeating the "retry is always safe, never a duplicate" guarantee across
 * exactly the reload/reopened-tab case it matters most for. Seeding the ref
 * from the hydrated draft closes that gap.
 */
function initialLastSentContent(draft: Draft): string | null {
  return draft.status === 'pending' || draft.status === 'unknown' ? draft.content : null;
}

export function useDraftStore(key: DraftKey) {
  const [draft, setDraft] = useState<Draft>(() => readStoredDraft(key));
  // Whether the MOST RECENT write attempt failed (e.g. private-browsing
  // sessionStorage quota) -- reflects the latest `persist()` call, not a
  // one-shot capability probe, since availability can change mid-session.
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const lastSentContentRef = useRef<string | null>(initialLastSentContent(draft));
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
    const nextDraft = readStoredDraft(key);
    lastSentContentRef.current = initialLastSentContent(nextDraft);
    setDraft(nextDraft);
    // A fresh conversation gets a fresh read, not the last conversation's
    // write-failure verdict.
    setStorageUnavailable(false);
  }, [key]);

  const update = useCallback(
    (patch: Partial<Draft>) => {
      setDraft((prev) => {
        const next = { ...prev, ...patch };
        setStorageUnavailable(!persist(key, next));
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
    setStorageUnavailable(!persist(key, next));
    setDraft(next);
    return id;
  }, [key, draft]);

  const acknowledge = useCallback(
    (clientRequestId: string) => {
      setDraft((prev) => {
        if (prev.clientRequestId !== clientRequestId) return prev; // stale ack, ignore
        setStorageUnavailable(!persist(key, EMPTY_DRAFT));
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
        setStorageUnavailable(!persist(key, next));
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
        setStorageUnavailable(!persist(key, next));
        return next;
      });
    },
    [key]
  );

  const discard = useCallback(() => {
    setStorageUnavailable(!persist(key, EMPTY_DRAFT));
    setDraft(EMPTY_DRAFT);
  }, [key]);

  return {
    draft,
    setContent,
    beginSend,
    acknowledge,
    reject,
    markUnknown,
    discard,
    storageUnavailable,
  };
}
