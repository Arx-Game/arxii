/**
 * Dialogs behind the node page's Add option, Copy node, Copy node and
 * everything after it, and Delete node buttons (#4558). Each shows the
 * server's plain message inline when the call is refused.
 */

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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

import {
  useCopyNode,
  useCopySubtree,
  useCreateMissionOption,
  useDeleteMissionNode,
  useDeleteMissionOption,
} from '../queries';
import type { MissionNode, MissionOption } from '../types';

const OPTION_KINDS = [
  { value: 'branch', label: 'Branch' },
  { value: 'check', label: 'Check' },
  { value: 'contest', label: 'Contest' },
  { value: 'external_act', label: 'External act' },
  { value: 'encounter', label: 'Encounter' },
] as const;

type OptionKindValue = (typeof OPTION_KINDS)[number]['value'];

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function errorText(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

function useResetOnOpen(open: boolean, reset: () => void) {
  useEffect(() => {
    if (open) reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
}

function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-sm text-destructive">
      {message}
    </p>
  );
}

interface AddOptionDialogProps extends DialogProps {
  nodeId: number;
  existingOptions: MissionOption[];
  onCreated: (option: MissionOption) => void;
}

export function AddOptionDialog({
  open,
  onOpenChange,
  nodeId,
  existingOptions,
  onCreated,
}: AddOptionDialogProps) {
  const [key, setKey] = useState('');
  const [kind, setKind] = useState<OptionKindValue>('branch');
  const [error, setError] = useState<string | null>(null);
  const create = useCreateMissionOption();
  useResetOnOpen(open, () => {
    setKey('');
    setKind('branch');
    setError(null);
  });

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) {
      setError('Give the option a key.');
      return;
    }
    const order = existingOptions.reduce((max, o) => Math.max(max, o.order), 0) + 1;
    try {
      const created = await create.mutateAsync({
        node: nodeId,
        key: trimmed,
        option_kind: kind,
        order,
        source_kind: 'authored',
      });
      onOpenChange(false);
      onCreated(created);
    } catch (e) {
      setError(errorText(e, 'Failed to add option'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add option</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="add-option-key">Option key</Label>
            <Input
              id="add-option-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              aria-invalid={error !== null}
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="add-option-kind">Option kind</Label>
            <Select value={kind} onValueChange={(v) => setKind(v as OptionKindValue)}>
              <SelectTrigger id="add-option-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OPTION_KINDS.map((k) => (
                  <SelectItem key={k.value} value={k.value}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <InlineError message={error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Add option
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface CopyDialogProps extends DialogProps {
  nodeId: number;
  onCreated: (node: MissionNode) => void;
}

export function CopyNodeDialog({ open, onOpenChange, nodeId, onCreated }: CopyDialogProps) {
  const [key, setKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const copy = useCopyNode();
  useResetOnOpen(open, () => {
    setKey('');
    setError(null);
  });

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) {
      setError('Give the copy a key.');
      return;
    }
    try {
      const created = await copy.mutateAsync({ id: nodeId, new_key: trimmed });
      onOpenChange(false);
      onCreated(created);
    } catch (e) {
      setError(errorText(e, 'Failed to copy node'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Copy node</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="copy-node-key">New node key</Label>
            <Input
              id="copy-node-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              aria-invalid={error !== null}
              autoFocus
            />
          </div>
          <InlineError message={error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={copy.isPending}>
              Copy node
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function CopySubtreeDialog({ open, onOpenChange, nodeId, onCreated }: CopyDialogProps) {
  const [prefix, setPrefix] = useState('');
  const [error, setError] = useState<string | null>(null);
  const copy = useCopySubtree();
  useResetOnOpen(open, () => {
    setPrefix('');
    setError(null);
  });

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = prefix.trim();
    if (!trimmed) {
      setError('Give the copies a key prefix.');
      return;
    }
    try {
      const created = await copy.mutateAsync({ id: nodeId, new_key_prefix: trimmed });
      onOpenChange(false);
      onCreated(created);
    } catch (e) {
      setError(errorText(e, 'Failed to copy node and everything after it'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Copy node and everything after it</DialogTitle>
            <DialogDescription>
              Copies this node and every node it leads on to. Each copy gets this prefix in front of
              its key.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="copy-subtree-prefix">Key prefix</Label>
            <Input
              id="copy-subtree-prefix"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              aria-invalid={error !== null}
              autoFocus
            />
          </div>
          <InlineError message={error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={copy.isPending}>
              Copy node and everything after it
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** One line of the delete-node list; ``id`` is a stable key, ``text`` what the author reads. */
export interface DeleteLink {
  id: string;
  text: string;
}

interface DeleteNodeDialogProps extends DialogProps {
  node: MissionNode;
  /** Links that become mission endings when this node goes. */
  endings: DeleteLink[];
  /** Random route destinations that disappear with this node. */
  lostDestinations: DeleteLink[];
  onDeleted: () => void;
}

export function DeleteNodeDialog({
  open,
  onOpenChange,
  node,
  endings,
  lostDestinations,
  onDeleted,
}: DeleteNodeDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const del = useDeleteMissionNode();
  useResetOnOpen(open, () => setError(null));

  const onConfirm = async () => {
    try {
      await del.mutateAsync(node.id);
      onOpenChange(false);
      onDeleted();
    } catch (e) {
      setError(errorText(e, 'Failed to delete node'));
    }
  };

  const hasLinks = endings.length > 0 || lostDestinations.length > 0;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete node</DialogTitle>
          <DialogDescription>
            {hasLinks
              ? `Delete node "${node.key}" and its options. These links lead here.`
              : `Delete node "${node.key}" and its options. Nothing leads here.`}
          </DialogDescription>
        </DialogHeader>
        {endings.length > 0 && (
          <div className="space-y-1">
            <p className="text-sm font-medium">These will become a mission ending</p>
            <ul className="list-disc pl-5 text-sm" data-testid="delete-node-endings">
              {endings.map((e) => (
                <li key={e.id}>{e.text}</li>
              ))}
            </ul>
          </div>
        )}
        {lostDestinations.length > 0 && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Random routes that lose this destination</p>
            <ul className="list-disc pl-5 text-sm" data-testid="delete-node-lost">
              {lostDestinations.map((e) => (
                <li key={e.id}>{e.text}</li>
              ))}
            </ul>
          </div>
        )}
        <InlineError message={error} />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={del.isPending}>
            Delete node
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface DeleteOptionDialogProps extends DialogProps {
  option: MissionOption;
  /** What to call the option in the question, from optionLabel. */
  label: string;
  onDeleted: () => void;
}

export function DeleteOptionDialog({
  open,
  onOpenChange,
  option,
  label,
  onDeleted,
}: DeleteOptionDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const del = useDeleteMissionOption();
  useResetOnOpen(open, () => setError(null));

  const onConfirm = async () => {
    try {
      await del.mutateAsync(option.id);
      onOpenChange(false);
      onDeleted();
    } catch (e) {
      setError(errorText(e, 'Failed to delete option'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete option</DialogTitle>
          <DialogDescription>
            {`Delete option "${label}" and its routes. Nothing else is removed.`}
          </DialogDescription>
        </DialogHeader>
        <InlineError message={error} />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={del.isPending}>
            Delete option
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
