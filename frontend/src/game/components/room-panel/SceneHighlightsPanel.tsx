import { useQuery } from '@tanstack/react-query';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { HighlightReel } from '@/scenes/components/HighlightReel';
import { fetchScene, sceneKeys } from '@/scenes/queries';
import type { SceneDetail } from '@/scenes/queries';

interface SceneHighlightsPanelProps {
  sceneId: number;
}

/**
 * Collapsed-by-default "Highlights" section for the /game right sidebar's
 * Room tab (#2161) — wraps the existing `HighlightReel` (previously mounted
 * only on `SceneDetailPage`) so scene applause surfaces in-context. Radix's
 * `AccordionContent` isn't rendered until expanded, so `HighlightReel`'s own
 * data fetch doesn't fire for players who never open the section.
 *
 * The WS `SceneSummary` GamePage threads down doesn't carry `viewer_can_gm`
 * (staff | scene GM | scene owner — see `serializers.get_viewer_can_gm`), so
 * this fetches the same scene-detail resource `SceneDetailPage` uses, sharing
 * its query cache via `sceneKeys.detail`.
 */
export function SceneHighlightsPanel({ sceneId }: SceneHighlightsPanelProps) {
  const { data: sceneDetail } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(String(sceneId)),
  });

  return (
    <Accordion type="single" collapsible className="border-b">
      <AccordionItem value="highlights" className="border-b-0">
        <AccordionTrigger className="px-3 py-2 text-xs font-semibold uppercase text-muted-foreground hover:no-underline">
          Highlights
        </AccordionTrigger>
        <AccordionContent className="px-3">
          <HighlightReel sceneId={String(sceneId)} canGm={sceneDetail?.viewer_can_gm} />
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
