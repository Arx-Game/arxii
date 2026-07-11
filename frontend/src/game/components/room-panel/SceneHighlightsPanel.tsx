import { useQuery } from '@tanstack/react-query';
import { HighlightReel } from '@/scenes/components/HighlightReel';
import { fetchScene, sceneKeys } from '@/scenes/queries';
import type { SceneDetail } from '@/scenes/queries';

interface SceneHighlightsPanelProps {
  sceneId: number;
}

/**
 * Mounts the existing `HighlightReel` (previously mounted only on
 * `SceneDetailPage`) in the `/game` right sidebar's Room tab (#2161) so
 * scene applause surfaces in-context. `HighlightReel` is already
 * collapsed-by-default and self-collapsing (its own header/chevron), so
 * this doesn't re-wrap it in another Accordion — a second stacked chevron
 * would force players through two clicks to see one thing, and its data
 * fetch already only fires once its own section is opened.
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

  return <HighlightReel sceneId={String(sceneId)} canGm={sceneDetail?.viewer_can_gm} />;
}
