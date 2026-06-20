/**
 * HighlightReel (#1241) — a scene's "what mattered here" summary.
 *
 * The whole reel is a collapsible section, collapsed by default (tidy + an extra spoiler
 * layer). Inside it: one *fully sealed* featured moment and a ranked index of the rest.
 * Sealed means the collapsed card reveals nothing — no pose, type, participants, or
 * reaction count — until the viewer chooses to reveal it, at which point the pose is
 * fetched through the existing interaction-detail endpoint (which re-checks visibility)
 * and rendered with the standard PoseUnit. An empty reel renders nothing.
 *
 * Featured selection + visibility filtering happen server-side; this component only ever
 * receives interaction ids it is allowed to reveal.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Sparkles, ChevronDown, ChevronRight, Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { PoseUnit } from './PoseUnit';
import { fetchHighlightReel, fetchInteraction } from '../queries';
import type { HighlightReel as HighlightReelData } from '../types';

interface SealedMomentProps {
  interactionId: number;
  sceneId: string;
  /** The text shown on the still-sealed card. The featured card uses a neutral label. */
  label: string;
  canGm?: boolean;
}

function SealedMoment({ interactionId, sceneId, label, canGm }: SealedMomentProps) {
  const [revealed, setRevealed] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['interaction', interactionId],
    queryFn: () => fetchInteraction(interactionId),
    enabled: revealed,
  });

  if (!revealed) {
    return (
      <button
        type="button"
        onClick={() => setRevealed(true)}
        aria-expanded={false}
        className={cn(
          'flex w-full items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2',
          'text-left text-sm text-foreground transition-colors hover:bg-muted'
        )}
      >
        <Eye className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="flex-1">{label}</span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setRevealed(false)}
        aria-expanded
        className={cn(
          'flex items-center gap-1.5 text-xs text-muted-foreground',
          'transition-colors hover:text-foreground'
        )}
      >
        <EyeOff className="h-3.5 w-3.5" />
        Hide
      </button>
      {isLoading && <Skeleton className="h-24 w-full" />}
      {isError && <p className="text-sm text-muted-foreground">Couldn’t load this moment.</p>}
      {data && <PoseUnit interaction={data} sceneId={sceneId} canGm={canGm} />}
    </div>
  );
}

export interface HighlightReelProps {
  sceneId: string;
  /** Threaded to revealed poses so a GM can still tag from the reel (#1139). */
  canGm?: boolean;
}

export function HighlightReel({ sceneId, canGm }: HighlightReelProps) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery<HighlightReelData>({
    queryKey: ['highlight-reel', sceneId],
    queryFn: () => fetchHighlightReel(sceneId),
  });

  // Empty reel (no tagged moments, no reacted poses) — render nothing.
  if (!data || (!data.featured && data.index.length === 0)) {
    return null;
  }

  return (
    <Card className="mt-3 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-2 text-sm font-medium',
          'transition-colors hover:bg-muted/50'
        )}
      >
        <Sparkles className="h-4 w-4 text-amber-500" />
        <span className="flex-1 text-left">Highlight Reel</span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {open && (
        <div className="space-y-3 border-t border-border px-3 py-3">
          {data.featured && (
            <SealedMoment
              interactionId={data.featured.interaction_id}
              sceneId={sceneId}
              label="✦ Top moment of this scene — reveal"
              canGm={canGm}
            />
          )}
          {data.index.length > 0 && (
            <ol className="space-y-2">
              {data.index.map((entry) => (
                <li key={entry.interaction_id}>
                  <SealedMoment
                    interactionId={entry.interaction_id}
                    sceneId={sceneId}
                    label={`Moment #${entry.rank} — reveal`}
                    canGm={canGm}
                  />
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  );
}
