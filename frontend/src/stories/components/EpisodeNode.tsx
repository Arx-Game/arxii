/**
 * EpisodeNode — custom React Flow node for episode DAG.
 *
 * Each node displays the chapter + episode breadcrumb and the episode title.
 * Clicking anywhere on the node triggers the onEpisodeClick callback, passing
 * the EpisodeLike object so the parent can open EpisodeFormDialog.
 *
 * Typing: React Flow v12 expects NodeProps<Node<DataType>>. We use the
 * plain NodeProps<Node> (generic) and cast data inside to our interface to
 * avoid re-exporting complex generics across the module boundary.
 */

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import type { EpisodeLike } from './EpisodeFormDialog';

export interface EpisodeNodeData extends Record<string, unknown> {
  /** Rendered breadcrumb: "Ch1 · Ep 2" style */
  breadcrumb: string;
  /** Episode title */
  title: string;
  /** Whether this is a virtual "Frontier" sink node */
  isFrontier?: boolean;
  /** The episode object — undefined for frontier nodes */
  episode?: EpisodeLike;
  /** Callback fired when user clicks the node */
  onEpisodeClick?: (episode: EpisodeLike) => void;
}

// Alias for the React Flow Node type specialised to our data.
export type EpisodeNodeType = Node<EpisodeNodeData>;

function EpisodeNodeComponent({ data }: NodeProps<EpisodeNodeType>) {
  if (data.isFrontier) {
    return (
      <div
        className="rounded-md border border-dashed border-muted-foreground/40 bg-muted/30 px-3 py-1.5 text-center text-xs text-muted-foreground"
        style={{ minWidth: 80 }}
        data-testid="dag-frontier-node"
      >
        Frontier
        <Handle type="target" position={Position.Top} className="!opacity-0" />
      </div>
    );
  }

  function handleClick() {
    if (data.episode !== undefined && data.onEpisodeClick) {
      data.onEpisodeClick(data.episode);
    }
  }

  return (
    <div
      className="cursor-pointer rounded-md border border-border bg-card px-3 py-2 shadow-sm transition-colors hover:border-primary/60 hover:bg-accent"
      style={{ minWidth: 120, maxWidth: 200 }}
      onClick={handleClick}
      data-testid="dag-episode-node"
      data-episode-id={data.episode?.id}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {data.breadcrumb}
      </p>
      <p className="truncate text-xs font-semibold text-foreground">{data.title}</p>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}

export const EpisodeNode = memo(EpisodeNodeComponent);
