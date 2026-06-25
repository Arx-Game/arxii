import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { editRoom } from '@/game/api/roomEditor';

interface RoomEditorPanelProps {
  characterId: number;
  initialName: string;
  initialDescription: string;
  initialIsPublic: boolean;
  /** Called after a successful save (e.g. to close the dialog + refresh the room). */
  onSaved: () => void;
  onCancel: () => void;
}

/**
 * Owner-facing room editor (#1470): edit the current room's name, description,
 * and public/private listing. Renders inside a dialog hosted by RoomPanel, shown
 * only when the viewer's active persona owns the room. Submits via the `edit_room`
 * action dispatch; ownership + the public-toggle guard are enforced server-side.
 */
export function RoomEditorPanel({
  characterId,
  initialName,
  initialDescription,
  initialIsPublic,
  onSaved,
  onCancel,
}: RoomEditorPanelProps) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [isPublic, setIsPublic] = useState(initialIsPublic);

  const mutation = useMutation({
    mutationFn: () =>
      editRoom(characterId, { name: name.trim(), description, is_public: isPublic }),
    onSuccess: (message) => {
      toast.success(message);
      onSaved();
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    mutation.mutate();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="room-name">Room name</Label>
        <Input id="room-name" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="space-y-2">
        <Label htmlFor="room-description">Description</Label>
        <Textarea
          id="room-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={6}
        />
      </div>
      <div className="flex items-center gap-3">
        <Switch id="room-public" checked={isPublic} onCheckedChange={setIsPublic} />
        <Label htmlFor="room-public">Public — listed on where; only public scenes here</Label>
      </div>
      <div className="flex gap-3">
        <Button type="submit" disabled={!name.trim() || mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save'}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
