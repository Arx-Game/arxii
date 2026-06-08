/**
 * Spread a Tale dialog (#745). Pick a deed you know of, write the telling,
 * choose how hard you push, and tell it in your current scene. The telling +
 * outcome echo into the scene feed; this dialog shows a qualitative ack.
 */
import { Loader2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useAppSelector } from '@/store/hooks';

import {
  useSaveDeedStoryMutation,
  useSceneActivityQuery,
  useSpreadableDeedsQuery,
  useSpreadMutation,
  useSpreadSpecializationsQuery,
  type SpreadResult,
} from './queries';

const NO_FORM = 'none';

const EFFORT_OPTIONS = [
  { value: 'low', label: 'Lightly' },
  { value: 'medium', label: 'Measured' },
  { value: 'high', label: 'Pour yourself in' },
  { value: 'extreme', label: 'Everything you have' },
];

export function SpreadTaleDialog({ personaId }: { personaId: number }) {
  const [open, setOpen] = useState(false);
  const active = useAppSelector((s) => s.game.active);
  const scene = useAppSelector((s) => (active ? (s.game.sessions[active]?.scene ?? null) : null));
  const sceneId = scene?.id ?? null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Spread a Tale
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Spread a Tale</DialogTitle>
        </DialogHeader>
        {sceneId === null ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            You must be in a scene to tell a tale. Step into a room and try again.
          </p>
        ) : (
          <SpreadForm
            key={`${sceneId}-${open}`}
            personaId={personaId}
            sceneId={sceneId}
            open={open}
            onDone={() => setOpen(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface FormProps {
  personaId: number;
  sceneId: number;
  open: boolean;
  onDone: () => void;
}

function SpreadForm({ personaId, sceneId, open, onDone }: FormProps) {
  const { data: deeds, isLoading } = useSpreadableDeedsQuery(personaId, open);
  const { data: forms } = useSpreadSpecializationsQuery(open);
  const { data: activity } = useSceneActivityQuery(sceneId, open);
  const [deedId, setDeedId] = useState<number | null>(null);
  const [pose, setPose] = useState('');
  const [effort, setEffort] = useState('medium');
  const [formId, setFormId] = useState<string>(NO_FORM);
  const [result, setResult] = useState<SpreadResult | null>(null);
  const mutation = useSpreadMutation(personaId);
  const saveStory = useSaveDeedStoryMutation(personaId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!deeds || deeds.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        You know of no tales worth telling here.
      </p>
    );
  }

  if (result) {
    const canSaveAccount = deedId !== null && pose.trim().length > 0;
    return (
      <div className="space-y-4">
        <p className="text-sm">
          The telling lands: <strong>{result.outcome}</strong>, in a {result.band.toLowerCase()}{' '}
          room.
        </p>
        {canSaveAccount &&
          (saveStory.isSuccess ? (
            <p className="text-sm text-muted-foreground">Saved to this deed&apos;s accounts.</p>
          ) : (
            <div className="space-y-1">
              <Button
                variant="outline"
                size="sm"
                disabled={saveStory.isPending}
                onClick={() => saveStory.mutate({ deed: deedId, text: pose })}
              >
                {saveStory.isPending ? 'Saving…' : 'Save this telling as your account'}
              </Button>
              {saveStory.isError && (
                <p className="text-sm text-destructive">{(saveStory.error as Error).message}</p>
              )}
            </div>
          ))}
        <DialogFooter>
          <Button onClick={onDone}>Done</Button>
        </DialogFooter>
      </div>
    );
  }

  const submit = () => {
    if (deedId === null) {
      return;
    }
    mutation.mutate(
      {
        scene: sceneId,
        deed: deedId,
        pose_text: pose,
        effort_level: effort,
        specialization: formId === NO_FORM ? null : Number(formId),
      },
      { onSuccess: setResult }
    );
  };

  return (
    <div className="space-y-4">
      {activity && (
        <p className="text-sm text-muted-foreground">The room is {activity.band.toLowerCase()}.</p>
      )}

      <Select value={deedId?.toString() ?? ''} onValueChange={(v) => setDeedId(Number(v))}>
        <SelectTrigger aria-label="Tale to spread">
          <SelectValue placeholder="Choose a tale to tell" />
        </SelectTrigger>
        <SelectContent>
          {deeds.map((d) => (
            <SelectItem key={d.id} value={d.id.toString()}>
              {d.title}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {forms && forms.length > 0 && (
        <Select value={formId} onValueChange={setFormId}>
          <SelectTrigger aria-label="Form of telling">
            <SelectValue placeholder="Form (optional)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_FORM}>No particular form</SelectItem>
            {forms.map((f) => (
              <SelectItem key={f.id} value={f.id.toString()}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <Textarea
        value={pose}
        onChange={(e) => setPose(e.target.value)}
        placeholder="How do you tell it? A song, a rousing speech, a whispered rumor..."
        aria-label="How you tell it"
        maxLength={2000}
        rows={4}
      />

      <Select value={effort} onValueChange={setEffort}>
        <SelectTrigger aria-label="Effort">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {EFFORT_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {mutation.isError && (
        <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
      )}

      <DialogFooter>
        <Button onClick={submit} disabled={deedId === null || mutation.isPending}>
          {mutation.isPending ? 'Telling…' : 'Tell the tale'}
        </Button>
      </DialogFooter>
    </div>
  );
}
