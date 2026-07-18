/**
 * StoryAreaListPanel — left rail of the GM story-builder canvas (#2450): the
 * GM's own story areas.
 *
 * A GM story area is always flat — `CreateStoryAreaAction` never sets a
 * parent (`world.gm.story_services.create_story_area` hardcodes
 * `level=AreaLevel.BUILDING`, no `parent`) — so this is a plain list, not
 * world-builder's recursive `AreaTreePanel`. Reusing `AreaTreePanel` here
 * would mean overriding both its hardwired data source
 * (`useWorldBuilderAreasQuery`, staff `/api/world-builder/areas/`) and its
 * whole nested-children UI, which has zero applicability to a set of areas
 * that can never have children — that's "thread a prop deep," not "hide a
 * staff-only control," so per the #2450 Task 10 brief this is a small
 * dedicated component instead. Hits `/api/gm/story-areas/` via
 * `useStoryAreasQuery`.
 */
import { Plus, Trash2 } from 'lucide-react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { useStoryAreasQuery } from '../queries';

export interface StoryAreaListPanelProps {
  selectedAreaId: number | null;
  onSelectArea: (areaId: number) => void;
  onCreateArea: () => void;
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

export function StoryAreaListPanel({
  selectedAreaId,
  onSelectArea,
  onCreateArea,
  runAction,
}: StoryAreaListPanelProps) {
  const { data, isLoading } = useStoryAreasQuery();
  const areas = data?.results ?? [];

  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2"
      data-testid="story-area-list-panel"
    >
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold">My Story Areas</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={onCreateArea}
          title="New story area"
          data-testid="story-area-list-new"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {isLoading && <p className="px-1 text-xs text-muted-foreground">Loading…</p>}
      {!isLoading && areas.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">No story areas yet.</p>
      )}
      {areas.map((area) => (
        <div
          key={area.id}
          className={cn(
            'flex items-center gap-1 rounded px-1 py-0.5 hover:bg-accent',
            selectedAreaId === area.id && 'bg-accent'
          )}
        >
          <button
            type="button"
            className="flex-1 truncate text-left text-sm"
            onClick={() => onSelectArea(area.id)}
            data-testid="story-area-list-node"
            data-area-id={area.id}
          >
            {area.name}
          </button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-5 w-5 p-0"
                title={`Remove ${area.name}`}
                data-testid={`story-area-list-remove-${area.id}`}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remove {area.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Refused if the area still has rooms in it — remove those first. This cannot be
                  undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => runAction('remove_story_area', { area_id: area.id })}
                >
                  Remove it
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      ))}
    </div>
  );
}
