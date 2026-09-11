import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

const INITIAL_PAGE_SIZE = 20;
import { ChevronDown, ChevronRight, MessageCircle, Reply } from 'lucide-react';
import { SceneMessages } from '@/scenes/components/SceneMessages';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { ConversationAnchorState } from '../playPreferences';
import {
  loadConversationAnchor,
  saveConversationAnchor,
  usePlayPreferences,
} from '../playPreferences';
import { usePoseReadTracking } from '../hooks/usePoseReadTracking';
import { markConversationRead } from '../playQueries';

/**
 * Wraps one rendered pose in the element `usePoseReadTracking` dwell-tracks.
 *
 * In Chronological view the row wrapper already carries
 * `ref={chronoVirtualizer.measureElement}` (Task 10) — a second, different
 * `ref` on the same element would silently drop one of the two assignments.
 * Rather than merge refs, this wraps just the pose's own content in its own
 * inner element nested inside that row, so the virtualizer keeps measuring
 * the row and this component independently dwell-tracks the pose within it.
 * In Threads view there's no existing ref to collide with, but the same
 * wrapper is reused there for one code path instead of two.
 */
function PoseReadTarget({
  pose,
  observe,
  children,
}: {
  pose: { id: number; timestamp: string };
  observe: (element: HTMLElement, pose: { id: number; timestamp: string }) => () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    return observe(element, pose);
    // Depend on pose.id/pose.timestamp (stable primitives), not the pose
    // object itself: the caller passes a fresh `{ id, timestamp }` literal
    // on every render, so an object-identity dep would re-run this effect
    // (and thus unobserve/re-observe the element) every render instead of
    // only when the pose actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [observe, pose.id, pose.timestamp]);
  // `data-pose-id` is the stable DOM handle the anchor system (#3759 Wave 6)
  // uses to find "the pose the user was reading" again after a resize, font
  // change, or history-page insertion -- see findScrollContainer/
  // findTopVisiblePoseId below.
  return (
    <div ref={ref} data-pose-id={pose.id}>
      {children}
    </div>
  );
}

/**
 * Walks up from `start` to find the nearest scrollable ancestor (the element
 * whose content actually overflows). In Threads view the reader has no
 * scroll container of its own -- GameWindow.tsx's `feedScrollRef` div is the
 * real one -- so anchor save/restore locates it this way rather than
 * threading a ref down through GameWindow, which would couple the two
 * components more tightly than the feature needs.
 */
function findScrollContainer(start: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = start;
  while (node) {
    if (node.scrollHeight > node.clientHeight) return node;
    node = node.parentElement;
  }
  return null;
}

/**
 * Finds the pose currently occupying the top of `container`'s visible area:
 * the last pose whose top edge has scrolled at or above the container's own
 * top (i.e. it's the one "in charge" of the top of the viewport), or the
 * very first pose if none have scrolled past yet. Returns the pose's id and
 * its offset (px, negative when partially scrolled past) relative to the
 * container's top -- the same coordinate space `offsetPx` is stored and
 * restored in.
 */
function findTopVisiblePoseId(container: HTMLElement): { poseId: string; offsetPx: number } | null {
  const poseEls = Array.from(container.querySelectorAll<HTMLElement>('[data-pose-id]'));
  if (poseEls.length === 0) return null;
  const containerTop = container.getBoundingClientRect().top;
  let best: HTMLElement | null = null;
  let bestOffset = -Infinity;
  for (const el of poseEls) {
    const offset = el.getBoundingClientRect().top - containerTop;
    if (offset <= 0 && offset > bestOffset) {
      bestOffset = offset;
      best = el;
    }
  }
  if (!best) {
    best = poseEls[0];
    bestOffset = best.getBoundingClientRect().top - containerTop;
  }
  const poseId = best.dataset.poseId;
  return poseId ? { poseId, offsetPx: bestOffset } : null;
}

interface ThreadedNarrativeReaderProps {
  sceneId: string;
  conversationKey: string;
  interactions: Interaction[];
  hasNextPage?: boolean;
  fetchNextPage: () => void;
  onAvatarClick?: (persona: PoseUnitAvatarClickPersona) => void;
  onAddTarget?: (name: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  onReply?: (interaction: Interaction) => void;
  readOnly?: boolean;
}

interface Group {
  key: string;
  interactions: Interaction[];
}

/** A wide, accessible reader for long-form scene poses. */
export function ThreadedNarrativeReader({
  sceneId,
  conversationKey,
  interactions,
  hasNextPage,
  fetchNextPage,
  onAvatarClick,
  onAddTarget,
  onAttachAction,
  onReply,
  readOnly = false,
}: ThreadedNarrativeReaderProps) {
  const [historyStartOverride, setHistoryStartOverride] = useState<number | null>(null);
  const historyStart = historyStartOverride ?? Math.max(0, interactions.length - INITIAL_PAGE_SIZE);
  const visibleInteractions = interactions.slice(historyStart);
  const groups = useMemo(() => {
    const grouped = new Map<string, Interaction[]>();
    for (const interaction of visibleInteractions) {
      // Legacy interactions have no reply topology and therefore each remain
      // an independent root. Only explicit server thread ids group replies.
      const key = interaction.thread_id || `legacy:${interaction.id}`;
      const rows = grouped.get(key) ?? [];
      rows.push(interaction);
      grouped.set(key, rows);
    }
    return [...grouped.entries()]
      .map(
        ([key, rows]): Group => ({
          key,
          interactions: [...rows].sort(
            (a, b) => a.timestamp.localeCompare(b.timestamp) || a.id - b.id
          ),
        })
      )
      .sort(
        (a, b) =>
          a.interactions[0].timestamp.localeCompare(b.interactions[0].timestamp) ||
          a.interactions[0].id - b.interactions[0].id
      );
  }, [visibleInteractions]);
  const storedAnchorState = useMemo(
    () => loadConversationAnchor(conversationKey),
    [conversationKey]
  );
  // The "collapse all but the most recently active thread" default can only
  // be computed once real thread data has arrived. On a real page load this
  // component mounts (keyed by conversationKey/sceneId, per GameWindow.tsx)
  // the instant sceneId becomes truthy, while useSceneInteractions's
  // useInfiniteQuery is still in flight — so `groups` is empty on that first
  // render. A lazy useState initializer only ever sees that one, empty
  // render and never re-runs once real data lands, so the default silently
  // never applies. Instead: seed synchronously from storage if it exists
  // (and never let the async default fire on top of restored state), else
  // leave `collapsed` empty and let the effect below apply the default the
  // first time `groups` is actually populated. `defaultSeeded` guards that
  // effect so it only ever runs once per mount — the user's own subsequent
  // toggles (via toggleThread/bulk expand-collapse) are the only thing
  // allowed to change `collapsed` after that.
  const [collapsed, setCollapsed] = useState<Set<string>>(() =>
    storedAnchorState ? new Set(storedAnchorState.collapsed) : new Set()
  );
  const defaultSeeded = useRef(storedAnchorState !== null);
  useEffect(() => {
    if (defaultSeeded.current) return;
    if (groups.length === 0) return;
    defaultSeeded.current = true;
    if (groups.length <= 1) {
      setCollapsed(new Set());
      return;
    }
    const mostRecentKey = [...groups].sort((a, b) =>
      b.interactions[b.interactions.length - 1].timestamp.localeCompare(
        a.interactions[a.interactions.length - 1].timestamp
      )
    )[0].key;
    setCollapsed(new Set(groups.filter((g) => g.key !== mostRecentKey).map((g) => g.key)));
  }, [groups]);
  const [collapsedPoses, setCollapsedPoses] = useState<Set<number>>(new Set());
  // Optimistic mirror of "Mark conversation read" (#3759 spec section 7): the
  // server call is fire-and-forget, like markPosesRead's dwell-tracked path,
  // so unread badges are cleared locally immediately rather than waiting on
  // whatever next refetches `interactions` -- a pose's timestamp is stable and
  // ISO-8601-sortable (same string-compare convention `groups`/`chronologicalItems`
  // already use above), so "was this pose covered by the last mark-read click"
  // is just a string comparison against the snapshot boundary sent to the server.
  const [locallyReadBefore, setLocallyReadBefore] = useState<string | null>(null);
  const isEffectivelyUnread = (item: Interaction) =>
    Boolean(item.is_unread) && (locallyReadBefore === null || item.timestamp > locallyReadBefore);
  const handleMarkConversationRead = () => {
    if (interactions.length === 0) return;
    const before = interactions.reduce(
      (latest, item) => (item.timestamp > latest ? item.timestamp : latest),
      interactions[0].timestamp
    );
    setLocallyReadBefore(before);
    markConversationRead(conversationKey, before).catch((error: unknown) => {
      console.error('Failed to mark conversation read', error);
    });
  };
  const { observe } = usePoseReadTracking();
  const { preferences, update } = usePlayPreferences();
  const chronological = preferences.readerMode === 'chronological';
  const chronologicalItems = useMemo(
    () =>
      [...visibleInteractions].sort(
        (a, b) => a.timestamp.localeCompare(b.timestamp) || a.id - b.id
      ),
    [visibleInteractions]
  );
  const chronoParentRef = useRef<HTMLDivElement>(null);
  const chronoVirtualizer = useVirtualizer({
    count: chronologicalItems.length,
    getScrollElement: () => chronoParentRef.current,
    estimateSize: () => 160,
    overscan: 8,
  });

  // Shared read-merge-write so a collapse toggle never clobbers a
  // concurrently-saved anchor (and vice versa): both sides of this feature
  // write the same localStorage row, so each write re-reads whatever the
  // OTHER side most recently saved instead of layering over a stale
  // mount-time snapshot (`storedAnchorState` is only ever fresh at mount).
  const persistAnchorState = (overrides: Partial<ConversationAnchorState>) => {
    const current = loadConversationAnchor(conversationKey);
    saveConversationAnchor(conversationKey, {
      anchor: 'anchor' in overrides ? (overrides.anchor ?? null) : (current?.anchor ?? null),
      collapsed: overrides.collapsed ?? current?.collapsed ?? [],
    });
  };
  const persistCollapsed = (next: Set<string>) => persistAnchorState({ collapsed: [...next] });
  const toggleThread = (key: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      persistCollapsed(next);
      return next;
    });
  const expandAllThreads = () => {
    const next = new Set<string>();
    setCollapsed(next);
    persistCollapsed(next);
  };
  const collapseAllThreads = () => {
    const next = new Set(groups.map((group) => group.key));
    setCollapsed(next);
    persistCollapsed(next);
  };
  const togglePose = (id: number) =>
    setCollapsedPoses((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // --- Reading-position anchors (#3759 Decision #3 / Wave 6) ---------------
  // The anchor identifies a pose (+ thread) and a pixel offset, never a raw
  // scrollTop -- so it survives resize, font/measure changes and
  // older-page-insertion, which all change *where* that same pose happens to
  // land on screen without changing *which pose* the reader should be
  // showing. `readOnlyRef`/`visibleInteractionsRef`/`collapsedRef` mirror the
  // latest render's values for the native (non-JSX) scroll listener below,
  // which is attached once per Threads-view session rather than
  // re-subscribed on every interaction/collapse change (re-subscribing would
  // risk dropping an in-flight debounce right when the user is mid-scroll).
  const rootRef = useRef<HTMLDivElement>(null);
  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;
  const visibleInteractionsRef = useRef(visibleInteractions);
  visibleInteractionsRef.current = visibleInteractions;
  const collapsedRef = useRef(collapsed);
  collapsedRef.current = collapsed;
  const conversationKeyRef = useRef(conversationKey);
  conversationKeyRef.current = conversationKey;

  const restoreThreadsAnchor = () => {
    const stored = loadConversationAnchor(conversationKeyRef.current);
    if (!stored?.anchor) return;
    const container = findScrollContainer(rootRef.current);
    if (!container) return;
    const target = container.querySelector<HTMLElement>(`[data-pose-id="${stored.anchor.poseId}"]`);
    // Best effort: the anchored pose isn't in the currently loaded set (e.g.
    // it lives on an older history page not yet fetched). Rather than fail
    // or guess, this leaves the reader at whatever position mount/pin-to-
    // bottom already left it at -- the acceptable fallback the spec allows.
    if (!target) return;
    const targetTop = target.getBoundingClientRect().top - container.getBoundingClientRect().top;
    container.scrollTop += targetTop - stored.anchor.offsetPx;
  };

  const restoreChronoAnchor = () => {
    const stored = loadConversationAnchor(conversationKeyRef.current);
    if (!stored?.anchor) return;
    const idx = chronologicalItems.findIndex((item) => String(item.id) === stored.anchor?.poseId);
    // Best effort, deliberately reduced scope (see file-level note above the
    // Chronological branch below): restores to the nearest loaded index at
    // the top of the viewport, not the exact recorded pixel offset. If the
    // pose isn't loaded at all, this leaves the virtualizer at its default
    // (latest-activity) position.
    if (idx === -1) return;
    chronoVirtualizer.scrollToIndex(idx, { align: 'start' });
  };

  const restoreAnchor = () => {
    if (chronological) restoreChronoAnchor();
    else restoreThreadsAnchor();
  };

  // Effect A: initial restore, once real pose data has arrived. Mirrors the
  // `defaultSeeded` pattern above -- this component can mount (keyed by
  // conversationKey/sceneId) before its interactions query resolves, so a
  // lazy useState initializer would only ever see that first empty render.
  // Guarded to fire at most once per mount so a later, unrelated arrival of
  // new poses doesn't yank the reader back to the anchor while the user is
  // reading elsewhere.
  const restoreSeeded = useRef(false);
  useEffect(() => {
    if (restoreSeeded.current) return;
    if (readOnly) return; // never restore into a historical reference view
    if (visibleInteractions.length === 0) return;
    restoreSeeded.current = true;
    restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, visibleInteractions.length]);

  // Effect B: "Return to live" (#3759 Decision #5). Re-applies the anchor
  // specifically on the readOnly:true -> false transition, regardless of
  // whether Effect A already ran -- GameWindow reuses this same component
  // instance across the reference/live boundary (same `conversationKey`), so
  // without this, returning to live would just leave the reader wherever
  // reading the historical reference left it.
  const prevReadOnlyRef = useRef(readOnly);
  useEffect(() => {
    const wasReadOnly = prevReadOnlyRef.current;
    prevReadOnlyRef.current = readOnly;
    if (wasReadOnly && !readOnly) restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly]);

  // Effect C: font/measure-change survival (#3759 Acceptance A08). A
  // proseSize/proseFamily/measure change doesn't move which pose the user
  // was reading -- only where it lands on screen -- so simply re-running the
  // same restore whenever one of these changes keeps the anchored pose in
  // the same relative viewport position after the change.
  useEffect(() => {
    if (readOnly) return;
    restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferences.proseSize, preferences.proseFamily, preferences.measure]);

  // Threads-view scroll listener: attaches once per Threads-view session
  // directly to the ancestor GameWindow.tsx owns (this reader has no scroll
  // container of its own in that view), debounced so a save only fires once
  // scrolling has settled rather than on every scroll tick.
  useEffect(() => {
    if (chronological) return;
    const container = findScrollContainer(rootRef.current);
    if (!container) return;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const handleScroll = () => {
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => {
        if (readOnlyRef.current) return; // never persist a reference-mode scroll
        const found = findTopVisiblePoseId(container);
        if (!found) return;
        const threadId =
          visibleInteractionsRef.current.find((item) => String(item.id) === found.poseId)
            ?.thread_id ?? null;
        persistAnchorState({
          anchor: { poseId: found.poseId, threadId, offsetPx: found.offsetPx },
          collapsed: [...collapsedRef.current],
        });
      }, 300);
    };
    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      container.removeEventListener('scroll', handleScroll);
      if (timeout) clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chronological]);

  // Chronological-view scroll handler: this view already owns its own scroll
  // container (`chronoParentRef`), so this is a plain onScroll prop rather
  // than a native listener -- no ancestor lookup needed.
  const chronoScrollTimeout = useRef<ReturnType<typeof setTimeout>>();
  const handleChronoScroll = () => {
    if (chronoScrollTimeout.current) clearTimeout(chronoScrollTimeout.current);
    chronoScrollTimeout.current = setTimeout(() => {
      if (readOnly) return;
      const container = chronoParentRef.current;
      if (!container) return;
      const found = findTopVisiblePoseId(container);
      if (!found) return;
      const threadId =
        visibleInteractions.find((item) => String(item.id) === found.poseId)?.thread_id ?? null;
      persistAnchorState({
        anchor: { poseId: found.poseId, threadId, offsetPx: found.offsetPx },
        collapsed: [...collapsed],
      });
    }, 300);
  };
  useEffect(
    () => () => {
      if (chronoScrollTimeout.current) clearTimeout(chronoScrollTimeout.current);
    },
    []
  );

  return (
    <div
      ref={rootRef}
      className="min-h-0 flex-1 [&_.text-sm]:text-[length:var(--play-prose-size,14px)]"
      aria-label="Story reader"
      style={{
        fontSize: 'var(--play-prose-size, 14px)',
        fontFamily: 'var(--play-prose-family, ui-sans-serif)',
      }}
    >
      <div className="mx-auto w-full max-w-[var(--play-reading-measure,90ch)] space-y-3 px-4 py-4">
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {groups.length
              ? `${groups.length} conversation${groups.length === 1 ? '' : 's'}`
              : 'New conversation'}
          </span>
          <div className="flex gap-2">
            {groups.length > 0 && (
              <>
                <button className="underline" onClick={expandAllThreads}>
                  Expand loaded threads
                </button>
                <button className="underline" onClick={collapseAllThreads}>
                  Collapse loaded threads
                </button>
              </>
            )}
            {interactions.length > 0 && (
              <button className="underline" onClick={handleMarkConversationRead}>
                Mark conversation read
              </button>
            )}
            <button
              className="underline"
              aria-pressed={chronological}
              onClick={() => update({ readerMode: chronological ? 'threads' : 'chronological' })}
            >
              {chronological ? 'Threads' : 'Chronological'}
            </button>
          </div>
        </div>
        {chronological &&
          (chronologicalItems.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <MessageCircle className="mx-auto h-6 w-6 text-muted-foreground" />
              <h2 className="mt-2 font-serif text-xl">Begin the scene</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Write the next part of the story below.
              </p>
            </div>
          ) : (
            // Anchor restore here is deliberately reduced-scope (#3759 Wave
            // 6): it calls chronoVirtualizer.scrollToIndex (see
            // restoreChronoAnchor above) rather than reproducing Threads
            // view's exact-pixel-offset restore. A virtualized list can't
            // measure an off-screen row until it's mounted, so landing on
            // the precise recorded offsetPx would need a further
            // measure/re-scroll pass once the target row renders; the
            // simpler nearest-index landing was judged good enough for this
            // less-used view. A follow-up wanting pixel parity here would
            // add that second pass once the target row's ref resolves.
            <div
              ref={chronoParentRef}
              onScroll={handleChronoScroll}
              data-testid="chrono-scroll-container"
              style={{ height: '70vh', overflow: 'auto' }}
            >
              <div style={{ height: chronoVirtualizer.getTotalSize(), position: 'relative' }}>
                {chronoVirtualizer.getVirtualItems().map((virtualRow) => {
                  const item = chronologicalItems[virtualRow.index];
                  const poseCollapsed = collapsedPoses.has(item.id);
                  return (
                    <div
                      key={item.id}
                      data-index={virtualRow.index}
                      ref={chronoVirtualizer.measureElement}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <PoseReadTarget
                        pose={{ id: item.id, timestamp: item.timestamp }}
                        observe={observe}
                      >
                        <p className="text-xs text-muted-foreground">
                          {item.thread_id ? 'In a thread' : 'Standalone'}
                        </p>
                        {poseCollapsed ? (
                          <article
                            className="mx-2 rounded border border-dashed px-3 py-2 text-sm"
                            data-testid={`collapsed-pose-${item.id}`}
                          >
                            <strong>{item.persona.name}</strong>
                            <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-muted-foreground">
                              {item.content}
                            </p>
                            <button
                              type="button"
                              className="mt-1 min-h-9 underline"
                              onClick={() => togglePose(item.id)}
                            >
                              Show full pose
                            </button>
                          </article>
                        ) : (
                          <SceneMessages
                            sceneId={sceneId}
                            filteredInteractions={[item]}
                            onAvatarClick={onAvatarClick}
                            onAddTarget={onAddTarget}
                            onAttachAction={onAttachAction}
                            readOnly={readOnly}
                          />
                        )}
                      </PoseReadTarget>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        {!chronological &&
          (groups.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <MessageCircle className="mx-auto h-6 w-6 text-muted-foreground" />
              <h2 className="mt-2 font-serif text-xl">Begin the scene</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Write the next part of the story below.
              </p>
            </div>
          ) : (
            groups.map((group) => {
              const root = group.interactions[0];
              const isCollapsed = collapsed.has(group.key);
              const unread = group.interactions.filter(isEffectivelyUnread).length;
              return (
                <section
                  key={group.key}
                  className="overflow-hidden rounded-lg border bg-card/60"
                  data-thread-id={group.key}
                >
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent/40"
                    aria-expanded={!isCollapsed}
                    aria-controls={`thread-${group.key}`}
                    onClick={() => toggleThread(group.key)}
                  >
                    {isCollapsed ? (
                      <ChevronRight className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {root?.persona.name ?? 'Conversation'}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {group.interactions.length}{' '}
                      {group.interactions.length === 1 ? 'pose' : 'poses'}
                    </span>
                    {unread > 0 && (
                      <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] text-primary-foreground">
                        {unread} new
                      </span>
                    )}
                  </button>
                  {!isCollapsed && (
                    <div id={`thread-${group.key}`} className="border-t px-2 py-2">
                      {group.interactions.map((item) => {
                        const poseCollapsed = collapsedPoses.has(item.id);
                        return (
                          <PoseReadTarget
                            key={`pose-${item.id}`}
                            pose={{ id: item.id, timestamp: item.timestamp }}
                            observe={observe}
                          >
                            {poseCollapsed ? (
                              <article
                                className="mx-2 rounded border border-dashed px-3 py-2 text-sm"
                                data-testid={`collapsed-pose-${item.id}`}
                              >
                                <strong>{item.persona.name}</strong>
                                <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-muted-foreground">
                                  {item.content}
                                </p>
                                <button
                                  type="button"
                                  className="mt-1 min-h-9 underline"
                                  onClick={() => togglePose(item.id)}
                                >
                                  Show full pose
                                </button>
                              </article>
                            ) : (
                              <>
                                <SceneMessages
                                  sceneId={sceneId}
                                  filteredInteractions={[item]}
                                  onAvatarClick={onAvatarClick}
                                  onAddTarget={onAddTarget}
                                  onAttachAction={onAttachAction}
                                  readOnly={readOnly}
                                />
                                <div className="flex items-center justify-end gap-2 px-2 text-xs text-muted-foreground">
                                  <button
                                    type="button"
                                    className="inline-flex min-h-9 items-center gap-1 underline"
                                    onClick={() => togglePose(item.id)}
                                  >
                                    Show less
                                  </button>
                                  {onReply && !readOnly && (
                                    <button
                                      type="button"
                                      className="inline-flex min-h-9 items-center gap-1 underline"
                                      onClick={() => onReply(item)}
                                    >
                                      <Reply className="h-3 w-3" /> Reply
                                    </button>
                                  )}
                                </div>
                              </>
                            )}
                          </PoseReadTarget>
                        );
                      })}
                    </div>
                  )}
                </section>
              );
            })
          ))}
        {(historyStart > 0 || hasNextPage) && (
          <div className="flex gap-2">
            {historyStart > 0 && (
              <button
                type="button"
                onClick={() =>
                  setHistoryStartOverride(Math.max(0, historyStart - INITIAL_PAGE_SIZE))
                }
                className="flex-1 rounded border px-3 py-2 text-sm"
              >
                Load earlier history
              </button>
            )}
            {historyStart < Math.max(0, interactions.length - INITIAL_PAGE_SIZE) && (
              <button
                type="button"
                onClick={() =>
                  setHistoryStartOverride(Math.max(0, interactions.length - INITIAL_PAGE_SIZE))
                }
                className="rounded border px-3 py-2 text-sm"
              >
                Jump to latest
              </button>
            )}
            {historyStart === 0 && hasNextPage && (
              <button
                type="button"
                onClick={fetchNextPage}
                className="flex-1 rounded border px-3 py-2 text-sm"
              >
                Load earlier history
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
