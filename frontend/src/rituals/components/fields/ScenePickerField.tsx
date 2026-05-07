/**
 * ScenePickerField — dropdown of the caller's active scenes.
 *
 * Uses fetchScenes from @/scenes/queries with status=active filter.
 * Each option's value is the scene id; label is the scene name.
 * onChange is called with the selected scene id (number).
 */

import { useQuery } from '@tanstack/react-query';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { fetchScenes } from '@/scenes/queries';
import type { SceneListItem } from '@/scenes/queries';
import type { FieldProps } from '@/rituals/types';

async function fetchActiveScenes(): Promise<{ results: SceneListItem[] }> {
  return (await fetchScenes('status=active')) as { results: SceneListItem[] };
}

export function ScenePickerField({ field, value, onChange, disabled }: FieldProps) {
  const { data, isLoading } = useQuery<{ results: SceneListItem[] }>({
    queryKey: ['scenes', 'active'],
    queryFn: fetchActiveScenes,
  });

  const scenes = data?.results ?? [];

  function handleChange(selectedValue: string) {
    onChange(Number(selectedValue));
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={handleChange}
        disabled={disabled || isLoading}
      >
        <SelectTrigger id={field.name}>
          <SelectValue placeholder={isLoading ? 'Loading scenes…' : 'Select a scene'} />
        </SelectTrigger>
        <SelectContent>
          {scenes.map((scene) => (
            <SelectItem key={scene.id} value={String(scene.id)}>
              {scene.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
