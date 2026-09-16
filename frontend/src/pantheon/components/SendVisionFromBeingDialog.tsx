/**
 * "Send Vision…" beside a god's pool (#3780): spending the being's pool and seeing how much
 * it has are one GM moment. The being is fixed; the recipient is picked by name from the
 * roster. The rest mirrors the sheet's SendVisionDialog (#3779).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
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
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useRosterSearch, useSendVisionFromBeing } from '../queries';

interface SendVisionFromBeingDialogProps {
  beingId: number;
  beingName: string;
}

export function SendVisionFromBeingDialog({ beingId, beingName }: SendVisionFromBeingDialogProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [recipient, setRecipient] = useState('');
  const [body, setBody] = useState('');
  const [reveal, setReveal] = useState(false);
  const { data: matches } = useRosterSearch(search);
  const mutation = useSendVisionFromBeing(beingId);

  const items = (matches ?? []).map((entry) => ({
    value: String(entry.character.id),
    label: entry.character.name,
  }));

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!recipient) {
      toast.error('Pick who receives it.');
      return;
    }
    if (!body.trim()) {
      toast.error('A vision needs its prose.');
      return;
    }
    mutation.mutate(
      { recipient: Number(recipient), being: beingId, body: body.trim(), reveal_source: reveal },
      {
        onSuccess: () => {
          toast.success('The vision is sent.');
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
        <Button data-testid="send-vision-button">Send Vision…</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>A vision from {beingName}</DialogTitle>
            <DialogDescription>
              Spends the being&apos;s pool; reaches the character at once or at login.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="vision-search">Find the character</Label>
            <Input
              id="vision-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Type a name…"
            />
            <Combobox
              items={items}
              value={recipient}
              onValueChange={setRecipient}
              placeholder="Pick the recipient"
              emptyMessage="No character matches."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="vision-from-being-body">Prose</Label>
            <Textarea
              id="vision-from-being-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={8}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="vision-from-being-reveal">Tell them which being sent it</Label>
            <Switch id="vision-from-being-reveal" checked={reveal} onCheckedChange={setReveal} />
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
