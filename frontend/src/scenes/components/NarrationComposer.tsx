/**
 * NarrationComposer — the narration composer dialog for one GM prompt (#4101,
 * demo Screen 2). Two independent sends: a private line to the chosen people
 * (prepared/authored when the prompt carries one, a blank line to compose
 * otherwise — every kind gets a private send, not just the ones with
 * authored text), and a room line everyone present can read. Each send is
 * its own `POST .../narrate/`; a failed send keeps its draft untouched and
 * the dialog stays open so the GM can try again or make the other send. A
 * successful send that still carries a `message` (e.g. the prompt closed
 * before the line landed, so it went out as plain narration) shows it as a
 * standing notice.
 *
 * Ruling R10-1: the Audience line is two static labels (the fixed send each
 * button makes), not a toggle — the people picker still edits who "Chosen
 * people" means for the private send.
 *
 * Demo-fidelity fix round (F2): after a send succeeds, its section shows a
 * clear sent state ("Sent to {names}."/"Sent to the room." plus the text
 * that went out) instead of leaving the quote/textarea looking blank and the
 * button greyed out. The GM can still write and send another line right
 * after -- the sent notice sits above a fresh, empty draft field.
 */
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useNarrateGMPrompt } from '../gmPromptQueries';
import type { GMPrompt, ScenePersona } from '../types';

export interface NarrationComposerProps {
  prompt: GMPrompt;
  sceneId: string;
  personas: ScenePersona[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NarrationComposer({
  prompt,
  sceneId,
  personas,
  open,
  onOpenChange,
}: NarrationComposerProps) {
  const narrate = useNarrateGMPrompt(sceneId);

  const [privateDraft, setPrivateDraft] = useState(prompt.private_text);
  const [editingPrivate, setEditingPrivate] = useState(false);
  const [roomDraft, setRoomDraft] = useState(prompt.room_text);
  const [chosen, setChosen] = useState<number[]>(
    prompt.subject_persona_id != null ? [prompt.subject_persona_id] : []
  );
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Sent-state (F2): what the last successful send carried, so the section
  // shows it was sent instead of going blank. The same lifecycle as
  // privateDraft/roomDraft above -- reset per prompt because GMPromptQueue
  // only ever mounts one open NarrationComposer at a time.
  const [privateSent, setPrivateSent] = useState<{ text: string; names: string } | null>(null);
  const [roomSent, setRoomSent] = useState<string | null>(null);

  function toggleChosen(id: number) {
    setChosen((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  function nameFor(id: number): string {
    if (id === prompt.subject_persona_id) return prompt.subject_name;
    return personas.find((persona) => persona.id === id)?.name ?? `#${id}`;
  }

  const chosenNames = chosen.map(nameFor).join(', ');

  function messageFrom(err: unknown): string {
    return err instanceof Error ? err.message : 'Failed to send narration';
  }

  async function sendPrivate(text: string) {
    setError(null);
    setNotice(null);
    try {
      const result = await narrate.mutateAsync({
        promptId: prompt.id,
        text,
        audience: 'chosen',
        receiver_persona_ids: chosen,
      });
      setPrivateSent({ text, names: chosenNames || 'the chosen people' });
      setPrivateDraft('');
      setEditingPrivate(false);
      if (result.message) setNotice(result.message);
    } catch (err) {
      setError(messageFrom(err));
    }
  }

  async function sendRoom() {
    setError(null);
    setNotice(null);
    try {
      const result = await narrate.mutateAsync({
        promptId: prompt.id,
        text: roomDraft,
        audience: 'room',
      });
      setRoomSent(roomDraft);
      setRoomDraft('');
      if (result.message) setNotice(result.message);
    } catch (err) {
      setError(messageFrom(err));
    }
  }

  // Ruling (Task 10 fix round 1, Important finding 1): every kind gets a
  // private send, not only the ones with authored private_text. When the
  // prompt carries none, skip straight to the blank-textarea editing view —
  // there is no prepared/authored text to preview or fall back to.
  const hasPreparedText = Boolean(prompt.private_text);
  // F2: once a private send has gone out, the box always falls to the
  // (now-blank) editing form -- there's nothing left to preview, and the GM
  // can still write another line.
  const showPrivateEditing = editingPrivate || privateSent !== null || !hasPreparedText;
  const privateSendDisabled = narrate.isPending || !privateDraft.trim();
  const roomSendDisabled = narrate.isPending || !roomDraft.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          {/* F5: "Tied to" is its own labelled chip line below, not folded
              into the title -- the title stays for the accessible name only. */}
          <DialogTitle className="sr-only">Narrate {prompt.kind_label}</DialogTitle>
          <DialogDescription>
            Two sends are offered here: a room line everyone present can read, and a private line to
            the people chosen.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Tied to
          </p>
          <span className="inline-flex w-fit items-center gap-1 rounded-full border border-border bg-muted/50 px-2 py-0.5 text-xs text-foreground">
            <span aria-hidden>✦</span>
            {prompt.subject_name
              ? `${prompt.kind_label}: ${prompt.subject_name}`
              : prompt.kind_label}
          </span>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Audience
          </p>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-border bg-muted/50 px-2 py-0.5 text-xs text-foreground">
              Everyone present
            </span>
            <span className="rounded-full border border-border bg-muted/50 px-2 py-0.5 text-xs text-foreground">
              Chosen people{chosenNames ? ` · ${chosenNames}` : ''}
            </span>
          </div>
          {personas.length > 0 && (
            <ul className="max-h-32 space-y-1 overflow-y-auto" data-testid="composer-persona-list">
              {personas.map((persona) => (
                <li key={persona.id}>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={chosen.includes(persona.id)}
                      onChange={() => toggleChosen(persona.id)}
                      className="h-4 w-4 rounded border-input"
                    />
                    {persona.name}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-2 rounded-md border border-border bg-card p-3">
          {hasPreparedText && (
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {prompt.prepared_for_character ? 'Prepared for this character' : 'Authored text'}
              </p>
              {prompt.prepared_for_character && (
                <Badge variant="outline" className="text-xs">
                  Prepared
                </Badge>
              )}
            </div>
          )}
          {privateSent && (
            <p role="status" data-testid="private-sent-notice" className="text-sm">
              Sent to {privateSent.names}.{' '}
              <span className="italic text-foreground">&ldquo;{privateSent.text}&rdquo;</span>
            </p>
          )}
          {showPrivateEditing ? (
            <>
              <Label
                htmlFor="narration-private-line"
                className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                Private line
              </Label>
              <Textarea
                id="narration-private-line"
                value={privateDraft}
                onChange={(event) => setPrivateDraft(event.target.value)}
              />
              <Button
                type="button"
                disabled={privateSendDisabled}
                onClick={() => sendPrivate(privateDraft)}
              >
                Send privately
              </Button>
            </>
          ) : (
            <>
              <blockquote
                data-testid="private-quote"
                className="border-l-2 border-primary pl-3 text-sm italic text-foreground"
              >
                &ldquo;{privateDraft}&rdquo;
              </blockquote>
              <div className="flex gap-2">
                <Button
                  type="button"
                  disabled={privateSendDisabled}
                  onClick={() => sendPrivate(privateDraft)}
                >
                  Send as is
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={narrate.isPending}
                  onClick={() => setEditingPrivate(true)}
                >
                  Edit before sending
                </Button>
              </div>
            </>
          )}
        </div>

        <div className="space-y-2">
          <Label
            htmlFor="narration-room-line"
            className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
          >
            Room line
          </Label>
          {roomSent && (
            <p role="status" data-testid="room-sent-notice" className="text-sm">
              Sent to the room.{' '}
              <span className="italic text-foreground">&ldquo;{roomSent}&rdquo;</span>
            </p>
          )}
          <Textarea
            id="narration-room-line"
            value={roomDraft}
            onChange={(event) => setRoomDraft(event.target.value)}
          />
          <Button type="button" disabled={roomSendDisabled} onClick={sendRoom}>
            Send to the room
          </Button>
        </div>

        {notice && (
          <p
            role="status"
            className="rounded-md border bg-muted/30 p-2 text-sm text-muted-foreground"
          >
            {notice}
          </p>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
