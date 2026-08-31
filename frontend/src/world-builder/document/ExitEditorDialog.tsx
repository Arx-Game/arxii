/**
 * ExitEditorDialog (#3477 Task 6) — opened from a Marginalia exit chip. Two
 * real actions, dispatched together on Save: `staff_rename_exit` (name only —
 * the action's actual signature has no aliases kwarg, unlike the brief's
 * loose phrasing; verified against `actions/definitions/world_builder.py`)
 * fires only when the name actually changed, and `staff_set_exit_detail`
 * (kind/openness/aliases together) always fires, since it's a plain
 * upsert-style set rather than a diffed rename.
 *
 * Lock/secrecy/watcher render as selects but stay permanently disabled with
 * `title="wired when the backing systems land"` — the backing models exist
 * (per the brief) but no builder action does yet, so wiring them up here
 * would mean inventing an action that isn't real. Honest stub, not a cut
 * corner.
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
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

import { EXIT_KINDS, type WorldBuilderExitDetail } from '../types';

const STUB_TITLE = 'wired when the backing systems land';

export interface ExitEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  exit: WorldBuilderExitDetail | null;
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

export function ExitEditorDialog({ open, onOpenChange, exit, runAction }: ExitEditorDialogProps) {
  const [name, setName] = useState('');
  const [aliases, setAliases] = useState('');
  const [kind, setKind] = useState('door');
  const [isOpen, setIsOpen] = useState(true);

  useEffect(() => {
    if (!open || !exit) return;
    setName(exit.name);
    setAliases(exit.aliases.join(', '));
    setKind(exit.kind);
    setIsOpen(exit.is_open);
  }, [open, exit]);

  if (!exit) return null;

  const save = () => {
    const trimmedName = name.trim();
    if (trimmedName && trimmedName !== exit.name) {
      runAction('staff_rename_exit', { exit_id: exit.id, name: trimmedName });
    }
    runAction('staff_set_exit_detail', {
      exit_id: exit.id,
      kind,
      is_open: isOpen,
      aliases,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogTitle>Exit: {exit.name}</DialogTitle>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="exit-editor-name">Name</Label>
            <Input
              id="exit-editor-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              data-testid="exit-editor-name"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="exit-editor-aliases">Aliases</Label>
            <Input
              id="exit-editor-aliases"
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
              placeholder="comma-separated"
              data-testid="exit-editor-aliases"
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="exit-editor-kind">Kind</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger id="exit-editor-kind" className="w-40" data-testid="exit-editor-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXIT_KINDS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="exit-editor-open">Open</Label>
            <Switch
              id="exit-editor-open"
              checked={isOpen}
              onCheckedChange={setIsOpen}
              data-testid="exit-editor-open"
            />
          </div>

          <p className="mt-1 font-body text-xs italic text-muted-foreground">
            The rest is sketched — the backing systems don't have a builder action yet.
          </p>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="exit-editor-lock">Lock</Label>
            <Select disabled>
              <SelectTrigger
                id="exit-editor-lock"
                className="w-40"
                title={STUB_TITLE}
                data-testid="exit-editor-lock"
              >
                <SelectValue placeholder="none" />
              </SelectTrigger>
              <SelectContent />
            </Select>
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="exit-editor-secrecy">Secrecy</Label>
            <Select disabled>
              <SelectTrigger
                id="exit-editor-secrecy"
                className="w-40"
                title={STUB_TITLE}
                data-testid="exit-editor-secrecy"
              >
                <SelectValue placeholder="visible" />
              </SelectTrigger>
              <SelectContent />
            </Select>
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="exit-editor-watcher">Watcher</Label>
            <Select disabled>
              <SelectTrigger
                id="exit-editor-watcher"
                className="w-40"
                title={STUB_TITLE}
                data-testid="exit-editor-watcher"
              >
                <SelectValue placeholder="none" />
              </SelectTrigger>
              <SelectContent />
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} data-testid="exit-editor-save">
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
