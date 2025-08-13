import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { SceneDetail, updateScene, finishScene } from '../queries';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';

interface Props {
  scene?: SceneDetail;
  onRefresh?: () => void;
}

export function SceneHeader({ scene, onRefresh }: Props) {
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();
  const { register, handleSubmit, reset } = useForm<{ name: string; description: string }>({
    defaultValues: { name: scene?.name ?? '', description: scene?.description ?? '' },
  });
  useEffect(() => {
    reset({ name: scene?.name ?? '', description: scene?.description ?? '' });
  }, [scene, reset]);
  const save = useMutation({
    mutationFn: (values: { name: string; description: string }) =>
      updateScene(String(scene?.id), values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scene', String(scene?.id)] });
      setEditing(false);
    },
  });
  const end = useMutation({
    mutationFn: () => finishScene(String(scene?.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scene', String(scene?.id)] });
      qc.invalidateQueries({ queryKey: ['scenes'] });
    },
  });

  if (!scene) return null;

  if (editing) {
    return (
      <form onSubmit={handleSubmit((values) => save.mutate(values))} className="mb-4 space-y-2">
        <div className="space-y-1">
          <label htmlFor="name" className="text-sm font-medium">
            Name
          </label>
          <Input id="name" {...register('name')} />
        </div>
        <div className="space-y-1">
          <label htmlFor="description" className="text-sm font-medium">
            Description
          </label>
          <Textarea id="description" {...register('description')} />
        </div>
        <div className="flex gap-2">
          <Button size="sm" type="submit" disabled={save.isPending}>
            Save
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div>
      <h1 className="mb-2 text-xl font-bold">{scene.name}</h1>
      <p className="mb-4">{scene.description}</p>
      {(scene.is_owner || scene.is_active) && (
        <div className="mb-2 flex gap-2">
          {scene.is_owner && (
            <>
              <Button size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
              {scene.is_active && (
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => end.mutate()}
                  disabled={end.isPending}
                >
                  End Scene
                </Button>
              )}
            </>
          )}
          {scene.is_active && (
            <Button size="sm" variant="outline" onClick={() => onRefresh?.()}>
              Refresh
            </Button>
          )}
        </div>
      )}
      {scene.is_active && (
        <p className="mb-4 text-xs text-muted-foreground">
          Auto-refreshes every minute while active
        </p>
      )}
      {scene.highlight_message && (
        <div className="mb-4 border bg-muted/20 p-2">
          <p className="font-semibold">Top Message:</p>
          <p>{scene.highlight_message.content}</p>
        </div>
      )}
    </div>
  );
}
