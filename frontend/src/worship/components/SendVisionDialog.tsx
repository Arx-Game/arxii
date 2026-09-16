/**
 * SendVisionDialog (#3779) — staff composes a vision for the character whose sheet this is.
 *
 * The being sending it, the prose, whether the recipient learns the source, and optionally
 * the prayer it answers (from the character's recent prayers), a Codex clue id, an episode
 * id. The server spends the being's pool and delivers; rarity is the GM's own restraint.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { useWorshippedBeings } from '@/character-creation/queries';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useSendVision } from '../queries';
import type { Prayer } from '../types';

interface SendVisionDialogProps {
  recipientSheetId: number;
  recipientName: string;
  prayers: Prayer[];
}

const NO_PRAYER = 'none';

function optionalId(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function SendVisionDialog({
  recipientSheetId,
  recipientName,
  prayers,
}: SendVisionDialogProps) {
  const [open, setOpen] = useState(false);
  const [beingId, setBeingId] = useState('');
  const [body, setBody] = useState('');
  const [reveal, setReveal] = useState(false);
  const [prayerId, setPrayerId] = useState(NO_PRAYER);
  const [clueRaw, setClueRaw] = useState('');
  const [episodeRaw, setEpisodeRaw] = useState('');
  const { data: beings } = useWorshippedBeings();
  const mutation = useSendVision();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!beingId) {
      toast.error('Choose the being that sends it.');
      return;
    }
    if (!body.trim()) {
      toast.error('A vision needs its prose.');
      return;
    }
    mutation.mutate(
      {
        recipient: recipientSheetId,
        being: Number(beingId),
        body: body.trim(),
        reveal_source: reveal,
        prayer: prayerId === NO_PRAYER ? null : Number(prayerId),
        clue: optionalId(clueRaw),
        episode: optionalId(episodeRaw),
      },
      {
        onSuccess: () => {
          toast.success(`A vision reaches ${recipientName}.`);
          setBody('');
          setOpen(false);
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="send-vision-button">
          Send vision
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Send {recipientName} a vision</DialogTitle>
            <DialogDescription>
              Prose from a god. It spends the being&apos;s pool and reaches the character at once,
              or at their next login.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="vision-being">From</Label>
            <Select value={beingId} onValueChange={setBeingId}>
              <SelectTrigger id="vision-being">
                <SelectValue placeholder="Choose a being" />
              </SelectTrigger>
              <SelectContent>
                {(beings ?? []).map((being) => (
                  <SelectItem key={being.id} value={String(being.id)}>
                    {being.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="vision-body">Prose</Label>
            <Textarea
              id="vision-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={8}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="vision-reveal">Tell them which being sent it</Label>
            <Switch id="vision-reveal" checked={reveal} onCheckedChange={setReveal} />
          </div>
          {prayers.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="vision-prayer">Answers a prayer</Label>
              <Select value={prayerId} onValueChange={setPrayerId}>
                <SelectTrigger id="vision-prayer">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_PRAYER}>None</SelectItem>
                  {prayers.map((prayer) => (
                    <SelectItem key={prayer.id} value={String(prayer.id)}>
                      To {prayer.being_name}: {prayer.text.slice(0, 60)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="vision-clue">Codex clue id (optional)</Label>
              <Input
                id="vision-clue"
                inputMode="numeric"
                value={clueRaw}
                onChange={(event) => setClueRaw(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="vision-episode">Episode id (optional)</Label>
              <Input
                id="vision-episode"
                inputMode="numeric"
                value={episodeRaw}
                onChange={(event) => setEpisodeRaw(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Sending…' : 'Send'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
