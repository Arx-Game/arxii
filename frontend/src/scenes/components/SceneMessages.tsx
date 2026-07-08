import { useState } from 'react';
import { PoseUnit } from './PoseUnit';
import type { Interaction } from '../types';
import type { ActionAttachmentInfo } from '../actionTypes';

interface Props {
  sceneId: string;
  filteredInteractions: Interaction[];
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  /** When true, shows the GM dramatic-moment tagging control on each pose (#1139). */
  canGm?: boolean;
}

/**
 * A thin divider shown for a run of consecutive muted interactions (#2087).
 * Click to expand — fetches the full content via the interaction detail endpoint.
 */
function MutedDivider({ count, ids }: { count: number; ids: number[] }) {
  const [expanded, setExpanded] = useState(false);
  const [revealedContent, setRevealedContent] = useState<Record<number, string> | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleExpand() {
    if (revealedContent !== null) {
      setExpanded(true);
      return;
    }
    setLoading(true);
    try {
      const { apiFetch } = await import('@/evennia_replacements/api');
      const results: Record<number, string> = {};
      for (const id of ids) {
        const res = await apiFetch(`/api/scenes/interactions/${id}/`);
        if (res.ok) {
          const data = await res.json();
          results[id] = data.content ?? '';
        }
      }
      setRevealedContent(results);
      setExpanded(true);
    } catch {
      // Silently fail — the divider stays collapsed.
    } finally {
      setLoading(false);
    }
  }

  if (expanded && revealedContent) {
    // Render the muted interactions inline with their revealed content.
    return null; // The parent re-renders these as normal PoseUnits.
  }

  return (
    <button
      onClick={handleExpand}
      disabled={loading}
      className="my-1 flex w-full items-center gap-2 px-4 py-1 text-xs text-muted-foreground hover:text-foreground"
      data-testid="muted-divider"
    >
      <span className="h-px flex-1 bg-border" />
      <span>{loading ? 'Loading…' : `${count} hidden · click to expand`}</span>
      <span className="h-px flex-1 bg-border" />
    </button>
  );
}

export function SceneMessages({
  sceneId,
  filteredInteractions,
  onAddTarget,
  onAttachAction,
  canGm,
}: Props) {
  // Collect the set of ACTION interaction IDs that are already embedded inside
  // a POSE via action_links. These are rendered inside their parent PoseUnit
  // and should be skipped at the top-level iteration to avoid duplication.
  const linkedActionIds = new Set<number>();
  for (const msg of filteredInteractions) {
    if (msg.action_links && msg.action_links.length > 0) {
      for (const link of msg.action_links) {
        linkedActionIds.add(link.action_interaction.id);
      }
    }
  }

  // Group consecutive muted interactions and insert dividers (#2087).
  type RenderItem =
    | { type: 'interaction'; msg: Interaction }
    | { type: 'divider'; count: number; ids: number[] };

  const items: RenderItem[] = [];
  let mutedRun: Interaction[] = [];

  function flushMutedRun() {
    if (mutedRun.length > 0) {
      items.push({
        type: 'divider',
        count: mutedRun.length,
        ids: mutedRun.map((m) => m.id),
      });
      // Also push the muted interactions themselves (with blanked content) so the
      // action/mode still shows. The divider is visual grouping, not exclusion.
      for (const m of mutedRun) {
        items.push({ type: 'interaction', msg: m });
      }
      mutedRun = [];
    }
  }

  for (const msg of filteredInteractions) {
    if (msg.mode === 'action' && linkedActionIds.has(msg.id)) {
      continue;
    }
    if (msg.is_muted) {
      mutedRun.push(msg);
    } else {
      flushMutedRun();
      items.push({ type: 'interaction', msg });
    }
  }
  flushMutedRun();

  return (
    <div>
      {items.map((item) => {
        if (item.type === 'divider') {
          return <MutedDivider key={`divider-${item.ids[0]}`} count={item.count} ids={item.ids} />;
        }
        const msg = item.msg;
        return (
          <PoseUnit
            key={msg.id}
            interaction={msg}
            sceneId={sceneId}
            onAddTarget={onAddTarget}
            onAttachAction={onAttachAction}
            canGm={canGm}
          />
        );
      })}
    </div>
  );
}
