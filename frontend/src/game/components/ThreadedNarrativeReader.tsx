import { useMemo, useState } from 'react';

const INITIAL_PAGE_SIZE = 20;
import { ChevronDown, ChevronRight, MessageCircle, Reply } from 'lucide-react';
import { SceneMessages } from '@/scenes/components/SceneMessages';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import {
  loadConversationAnchor,
  saveConversationAnchor,
  usePlayPreferences,
} from '../playPreferences';

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
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    if (storedAnchorState) return new Set(storedAnchorState.collapsed);
    if (groups.length <= 1) return new Set();
    const mostRecentKey = [...groups].sort((a, b) =>
      b.interactions[b.interactions.length - 1].timestamp.localeCompare(
        a.interactions[a.interactions.length - 1].timestamp
      )
    )[0].key;
    return new Set(groups.filter((g) => g.key !== mostRecentKey).map((g) => g.key));
  });
  const [collapsedPoses, setCollapsedPoses] = useState<Set<number>>(new Set());
  const { preferences, update } = usePlayPreferences();
  const chronological = preferences.readerMode === 'chronological';
  const chronologicalItems = useMemo(
    () =>
      [...visibleInteractions].sort(
        (a, b) => a.timestamp.localeCompare(b.timestamp) || a.id - b.id
      ),
    [visibleInteractions]
  );

  const toggleThread = (key: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveConversationAnchor(conversationKey, {
        anchor: storedAnchorState?.anchor ?? null,
        collapsed: [...next],
      });
      return next;
    });
  const togglePose = (id: number) =>
    setCollapsedPoses((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div
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
                <button className="underline" onClick={() => setCollapsed(new Set())}>
                  Expand loaded threads
                </button>
                <button
                  className="underline"
                  onClick={() => setCollapsed(new Set(groups.map((group) => group.key)))}
                >
                  Collapse loaded threads
                </button>
              </>
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
            chronologicalItems.map((item) => {
              const poseCollapsed = collapsedPoses.has(item.id);
              return (
                <div key={`chrono-${item.id}`}>
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
                </div>
              );
            })
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
              const unread = group.interactions.filter((item) => item.is_unread).length;
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
                          <div key={`pose-${item.id}`}>
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
                          </div>
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
