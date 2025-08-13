import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { SceneDetail, updateScene, finishScene } from '../queries';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';

interface Props {
  scene?: SceneDetail;
}

export function SceneHeader({ scene }: Props) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(scene?.name ?? '');
  const [description, setDescription] = useState(scene?.description ?? '');
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => updateScene(String(scene?.id), { name, description }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scene', String(scene?.id)] });
      setEditing(false);
    },
  });
  const end = useMutation({
    mutationFn: () => finishScene(String(scene?.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scene', String(scene?.id)] });
    },
  });

  if (!scene) return null;

  if (editing) {
    return (
      <div className="mb-4 space-y-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        <div className="flex gap-2">
          <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
            Save
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-2 text-xl font-bold">{scene.name}</h1>
      <p className="mb-4">{scene.description}</p>
      {scene.is_owner && (
        <div className="mb-4 flex gap-2">
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
        </div>
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
