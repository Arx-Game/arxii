import { useCallback, useEffect, useRef, useState } from 'react';

export interface DraftKey {
  accountId: number;
  personaId: number;
  conversationKey: string;
}

/**
 * What action type (say/whisper/tt/...) and target(s) a `pending`/`rejected`/
 * `unknown` attempt was actually sent under. Deliberately a minimal,
 * independent shape (not the frontend's `ComposerMode`, which also carries
 * UI-only `label`/`locked` fields) — this is the one piece of state a retry
 * MUST reproduce exactly, so it's persisted alongside `clientRequestId`
 * rather than re-derived from whatever the live composer mode happens to be
 * at retry time (#3760 Task 11 critical fix; see `beginSend`'s doc comment).
 */
export interface DraftMode {
  command: string;
  targets: string[];
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
  mode: DraftMode | null;
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
  mode: null,
};

const DRAFT_STORAGE_PREFIX = 'arx:play-draft:v2:';

export function draftStorageKey(key: DraftKey): string {
  return `${DRAFT_STORAGE_PREFIX}${key.accountId}:${key.personaId}:${key.conversationKey}`;
}

/**
 * Exported (#3760 Task 12 review fix) so a caller with its own draft state
 * can re-read the CURRENT persisted value before acting on stale in-memory
 * state — see `CommandInput.tsx`'s reconnect effect, which uses this to
 * detect when `useGameSocket`'s storage-level `reconcileStoredDrafts` scan
 * has already resolved this exact draft out from under a mounted composer.
 */
export function readStoredDraft(key: DraftKey): Draft {
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
 * `beginSend()`'s "same content as last time -> reuse the id (and mode)"
 * check compares against `lastSentContentRef`, an in-memory ref that starts
 * life empty on every mount. For a draft hydrated from storage already
 * `pending`/`rejected`/`unknown` (a stranded draft from a reload, #3760 Task
 * 11's Retry/"Resume & retry", or a plain Send on an untouched
 * `rejected`/`unknown` draft), that would otherwise mint a FRESH id -- and
 * capture whatever mode is live right now instead of the one it was
 * originally sent under -- on the first `beginSend()` after reload, even
 * though the content is unchanged from the original attempt. That defeats
 * BOTH the "retry is always safe, never a duplicate" id guarantee AND the
 * "an unmodified resend keeps its original mode" guarantee across exactly
 * the reload/reopened-tab case they matter most for. Seeding the ref from
 * the hydrated draft closes both gaps. Any NON-`clean` status qualifies
 * (not just `pending`/`unknown`): `clean` is the only status `setContent`
 * ever produces, so any other status means the content hasn't been edited
 * since the attempt that produced it.
 */
function initialLastSentContent(draft: Draft): string | null {
  return draft.status !== 'clean' ? draft.content : null;
}

interface StoredDraftEntry {
  storageKey: string;
  draft: Draft;
}

/** Every persisted draft (any conversation, any persona) not already `clean`. */
function listReconcilableDraftEntries(): StoredDraftEntry[] {
  const entries: StoredDraftEntry[] = [];
  let storageKeys: string[];
  try {
    storageKeys = Object.keys(sessionStorage);
  } catch {
    return entries;
  }
  for (const storageKey of storageKeys) {
    if (!storageKey.startsWith(DRAFT_STORAGE_PREFIX)) continue;
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) continue;
      const draft: Draft = { ...EMPTY_DRAFT, ...(JSON.parse(raw) as Partial<Draft>) };
      if (draft.status !== 'clean' && draft.clientRequestId) {
        entries.push({ storageKey, draft });
      }
    } catch {
      // Unparsable entry — skip it rather than fail the whole scan.
    }
  }
  return entries;
}

function removeAtStorageKey(storageKey: string): void {
  try {
    sessionStorage.removeItem(storageKey);
  } catch {
    // Storage unavailable — there is nothing stored to clean up either.
  }
}

/** Nothing composed and nothing in flight: safe to replace wholesale. */
function isBlankDraft(draft: Draft): boolean {
  return draft.content === '' && draft.status === 'clean' && draft.clientRequestId === null;
}

function persistAtStorageKey(storageKey: string, draft: Draft): boolean {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

/**
 * Non-hook reconciliation entry point (#3760 Task 12) for the reconnect-open
 * handler in `useGameSocket.ts`. That handler runs at module scope, outside
 * React entirely — it has no way to reach any particular mounted
 * `useDraftStore` instance (there may be zero, one, or several, one per open
 * conversation tab), so it cannot call `beginSend()`/`acknowledge()` through
 * a live hook. What it CAN reach is the same `sessionStorage` namespace every
 * `useDraftStore` instance reads and writes — this function scans that
 * namespace directly for every draft left `pending`/`rejected`/`unknown`
 * (i.e. anything a reconnect could have orphaned mid-send) and resolves each
 * via `lookup` (the Task 6 `GET /api/play/submissions/{client_request_id}/`
 * endpoint — the only reconciliation channel available at this call site;
 * resending via a reused id requires a live composer instance this function
 * cannot reach).
 *
 * A found record means the send landed while nobody was watching — the
 * stored draft is cleared exactly like `acknowledge()` would. A `null`
 * result ("no record") or a lookup failure leaves the stored draft
 * untouched: a mounted `CommandInput` for that conversation still owns its
 * own in-memory copy and resolves it through the normal ack/reject/stranded
 * path the next time it checks (Task 11's "Check status"/Task 12's
 * reconnect-triggered auto-check in `CommandInput.tsx`) — this function only
 * exists to stop an ALREADY-LANDED send from sitting there forever for a
 * conversation with no mounted composer left to notice. Both paths write
 * through the same storage format, so a race between this scan and a
 * concurrently-mounted composer's own check converges on the same answer
 * (the lookup is an idempotent GET).
 */
export async function reconcileStoredDrafts(
  lookup: (clientRequestId: string) => Promise<unknown | null>
): Promise<void> {
  const entries = listReconcilableDraftEntries();
  await Promise.allSettled(
    entries.map(async ({ storageKey, draft }) => {
      // Non-null guaranteed by listReconcilableDraftEntries's filter.
      const clientRequestId = draft.clientRequestId as string;
      try {
        const result = await lookup(clientRequestId);
        if (result) {
          persistAtStorageKey(storageKey, EMPTY_DRAFT);
        }
      } catch {
        // Ambiguous — leave the stored draft as-is for the composer's own
        // reconciliation surface to resolve.
      }
    })
  );
}

export interface DraftStoreOptions {
  /**
   * True while `key` is PROVISIONAL: this is a real conversation the caller
   * cannot fully name yet (#3784). `GameWindow`'s room-anchor composer is
   * the case — during "Entering world" the player is standing in a room the
   * client has not been told the id of, so the scope carries a
   * `room:unknown` placeholder until the first `room_state` broadcast.
   *
   * A key change AWAY from a provisional key is the same conversation
   * finally getting its name, so the draft moves with it instead of being
   * left stranded under the placeholder while the composer re-hydrates an
   * empty row. A key change away from a SETTLED key is an ordinary
   * conversation switch (walking through an exit, opening a tab) and
   * hydrates as usual — that separation is the whole point of keying the
   * draft on the room in the first place (#3760 Task 14).
   *
   * Without this, a draft typed during entry vanished the moment presence
   * arrived (`e2e/game-entry.spec.ts`).
   */
  provisional?: boolean;
}

export function useDraftStore(key: DraftKey, options: DraftStoreOptions = {}) {
  const { provisional = false } = options;
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
  // `provisional` as of the PREVIOUS render — the question this effect asks
  // is about the key being left behind, not the one being adopted.
  const wasProvisionalRef = useRef(provisional);
  useEffect(() => {
    const previousStorageKey = currentStorageKeyRef.current;
    const leavingProvisionalKey = wasProvisionalRef.current;
    wasProvisionalRef.current = provisional;
    const nextStorageKey = draftStorageKey(key);
    if (previousStorageKey === nextStorageKey) return;
    currentStorageKeyRef.current = nextStorageKey;
    // Read through the updater rather than the render closure so this effect
    // need not depend on `draft` and re-run on every keystroke.
    setDraft((previousDraft) => {
      if (leavingProvisionalKey && !isBlankDraft(previousDraft)) {
        // The same conversation, now identified: carry the live draft over
        // and drop the placeholder row, so nothing is left behind to
        // resurface later as a phantom stranded draft. The carried draft
        // wins over anything already stored under the new key — it is what
        // the player is looking at and about to send.
        setStorageUnavailable(!persist(key, previousDraft));
        removeAtStorageKey(previousStorageKey);
        return previousDraft;
      }
      const nextDraft = readStoredDraft(key);
      lastSentContentRef.current = initialLastSentContent(nextDraft);
      // A fresh conversation gets a fresh read, not the last conversation's
      // write-failure verdict.
      setStorageUnavailable(false);
      return nextDraft;
    });
  }, [key, provisional]);

  // The patch may be a function of the PREVIOUS draft (#3784) so a caller
  // whose new value depends on the current content -- `CommandInput`'s
  // `@target` append effect -- can express that without reading a stale
  // render closure, exactly as it would with a `setState` updater. A plain
  // object patch stays the common case.
  const update = useCallback(
    (patch: Partial<Draft> | ((previous: Draft) => Partial<Draft>)) => {
      setDraft((prev) => {
        const next = { ...prev, ...(typeof patch === 'function' ? patch(prev) : patch) };
        setStorageUnavailable(!persist(key, next));
        return next;
      });
    },
    [key]
  );

  const setContent = useCallback(
    (content: string | ((previous: string) => string)) =>
      // Editing invalidates whatever attempt is in flight: the outstanding
      // clientRequestId no longer names the current content, so a stale
      // ack/reject/unknown for it must not touch this newer, unsent edit.
      // `mode` is cleared right alongside it for the identical reason -- an
      // edit is a genuinely NEW attempt, free to pick up whatever mode is
      // live right now; only an UNCHANGED resend must keep the mode it was
      // originally composed under (#3760 Task 11 critical fix).
      update((previous) => ({
        content: typeof content === 'function' ? content(previous.content) : content,
        clientRequestId: null,
        status: 'clean',
        rejectionReason: null,
        mode: null,
      })),
    [update]
  );

  /**
   * `liveMode` is what the caller would send under RIGHT NOW if this were a
   * fresh attempt. Whether that's actually used depends on the SAME
   * `contentUnchanged` check that already governs `clientRequestId` reuse: an
   * unmodified retry preserves the STORED `mode` (from the original attempt)
   * and ignores `liveMode` entirely; a changed-content send captures
   * `liveMode` fresh, exactly like it mints a fresh id.
   *
   * This is the fix for a real privacy leak (#3760 Task 11 review): `Draft`
   * used to carry no mode/target info at all, so a stranded draft reloaded
   * mid-whisper had nothing to distinguish it from a pose/say once the
   * composer's live mode had moved on (a mode switch, or a fresh page load
   * whose composer defaults to the room tab) -- Retry/"Resume & retry", and
   * even a plain Send on an untouched `rejected`/`unknown` draft, would
   * silently redispatch a private whisper as a public say/pose. Callers MUST
   * treat this rule as the single source of truth for "what mode is this
   * send actually going out under" -- never read a live mode prop separately
   * at dispatch time once a `pending`/`rejected`/`unknown` draft exists.
   */
  const beginSend = useCallback(
    (liveMode: DraftMode | null = null): string => {
      // Computed from the current `draft` closure rather than inside a
      // setState updater: React does not guarantee the updater callback runs
      // synchronously, so a value it assigns is not safe to read immediately
      // after calling setDraft (only across a re-render).
      const contentUnchanged =
        lastSentContentRef.current === draft.content && draft.clientRequestId;
      const id = contentUnchanged ? (draft.clientRequestId as string) : crypto.randomUUID();
      const mode = contentUnchanged ? draft.mode : liveMode;
      lastSentContentRef.current = draft.content;
      const next: Draft = {
        ...draft,
        clientRequestId: id,
        status: 'pending',
        rejectionReason: null,
        mode,
      };
      setStorageUnavailable(!persist(key, next));
      setDraft(next);
      return id;
    },
    [key, draft]
  );

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
