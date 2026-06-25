import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import type { SceneDetail, SceneRoundModeValue } from '../types';
import { useSetRoundMode, type SetRoundModePayload } from '../queries';

const MODE_OPTIONS: { value: SceneRoundModeValue; label: string }[] = [
  { value: 'open', label: 'Open — every action resolves immediately' },
  { value: 'pose_order', label: 'Pose order — quorum advances the round' },
  { value: 'strict', label: 'Strict — declare, then resolve together' },
];

export function RoundSettingsDialog({ scene }: { scene: SceneDetail }) {
  const [open, setOpen] = useState(false);
  const round = scene.active_round;
  const mutation = useSetRoundMode(String(scene.id));

  const [mode, setMode] = useState<SceneRoundModeValue>(round?.mode ?? 'pose_order');
  const [quorum, setQuorum] = useState<number>(round?.advance_quorum_pct ?? 60);
  const [maxActions, setMaxActions] = useState<number>(round?.max_actions_per_round ?? 1);
  const [repeatLock, setRepeatLock] = useState<boolean>(round?.per_target_repeat_lock ?? false);

  // Re-sync local form state whenever the dialog opens or the round changes.
  useEffect(() => {
    if (round) {
      setMode(round.mode);
      setQuorum(round.advance_quorum_pct);
      setMaxActions(round.max_actions_per_round);
      setRepeatLock(round.per_target_repeat_lock);
    } else {
      setMode('pose_order');
      setQuorum(60);
      setMaxActions(1);
      setRepeatLock(false);
    }
  }, [round, open]);

  if (!scene.viewer_can_gm || !scene.is_active) return null;

  const noRound = round === null;
  // A danger round is an ordinary STRICT round (#1466): fully reconfigurable, just
  // started by an unfolding peril. We surface that context but never lock the controls.
  const isDanger = round?.is_danger ?? false;

  function handleSave() {
    const payload: SetRoundModePayload = {
      mode,
      advance_quorum_pct: quorum,
      max_actions_per_round: maxActions,
      per_target_repeat_lock: repeatLock,
    };
    mutation.mutate(payload, { onSuccess: () => setOpen(false) });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          Round settings
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Round settings</DialogTitle>
          <DialogDescription>Control how this scene&apos;s rounds resolve.</DialogDescription>
        </DialogHeader>

        {noRound ? (
          <p className="text-sm text-muted-foreground">
            There is no active round in this scene. Start a round before configuring it.
          </p>
        ) : (
          <div className="space-y-4">
            {isDanger && (
              <p className="text-xs text-muted-foreground">
                This round was started by an unfolding danger. It resolves each round and ends on
                its own once the peril clears — but you can still adjust its settings below.
              </p>
            )}

            <div className="space-y-1">
              <Label htmlFor="round-mode">Mode</Label>
              <Select value={mode} onValueChange={(v) => setMode(v as SceneRoundModeValue)}>
                <SelectTrigger id="round-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label htmlFor="round-quorum">Advance quorum (%)</Label>
              <Input
                id="round-quorum"
                type="number"
                min={0}
                max={100}
                value={quorum}
                onChange={(e) => setQuorum(Number(e.target.value))}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="round-max-actions">Max actions per round</Label>
              <Input
                id="round-max-actions"
                type="number"
                min={0}
                value={maxActions}
                onChange={(e) => setMaxActions(Number(e.target.value))}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="round-repeat-lock">Lock repeat actions on the same target</Label>
              <Switch id="round-repeat-lock" checked={repeatLock} onCheckedChange={setRepeatLock} />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button type="button" onClick={handleSave} disabled={noRound || mutation.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
