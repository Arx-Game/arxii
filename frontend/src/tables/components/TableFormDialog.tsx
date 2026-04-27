/**
 * TableFormDialog — create + edit table dialog.
 *
 * Create mode: triggered from TablesListPage (GM-only). GMProfile.id is passed
 * as the `gmProfileId` prop so the form can set gm=<id> on creation.
 *
 * Edit mode: triggered from TableDetailPage "Edit" button.
 */

import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useCreateTable, useUpdateTable } from '../queries';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  name?: string[];
  description?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CreateModeProps {
  mode: 'create';
  gmProfileId: number;
  children: React.ReactNode;
}

interface EditModeProps {
  mode: 'edit';
  table: GMTable;
  children: React.ReactNode;
}

type TableFormDialogProps = CreateModeProps | EditModeProps;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TableFormDialog(props: TableFormDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateTable();
  const updateMutation = useUpdateTable();

  const isEdit = props.mode === 'edit';
  const isPending = createMutation.isPending || updateMutation.isPending;

  // Populate form when opening in edit mode
  useEffect(() => {
    if (open && isEdit) {
      setName(props.table.name);
      setDescription(props.table.description ?? '');
    }
  }, [open, isEdit, isEdit ? props.table : null]); // eslint-disable-line react-hooks/exhaustive-deps

  function resetForm() {
    setName('');
    setDescription('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    if (isEdit) {
      updateMutation.mutate(
        { id: props.table.id, data: { name: name.trim(), description: description.trim() } },
        {
          onSuccess: () => {
            toast.success('Table updated');
            setOpen(false);
          },
          onError: async (err: unknown) => {
            const res = (err as { response?: Response })?.response;
            if (res) {
              const body = (await res.json()) as DRFFieldErrors;
              setFieldErrors(body);
            }
          },
        }
      );
    } else {
      createMutation.mutate(
        {
          gm: (props as CreateModeProps).gmProfileId,
          name: name.trim(),
          description: description.trim(),
        },
        {
          onSuccess: () => {
            toast.success('Table created');
            setOpen(false);
          },
          onError: async (err: unknown) => {
            const res = (err as { response?: Response })?.response;
            if (res) {
              const body = (await res.json()) as DRFFieldErrors;
              setFieldErrors(body);
            }
          },
        }
      );
    }
  }

  const isValid = name.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{props.children}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Table' : 'Create Table'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Update the name or description of your table.'
              : 'Create a new GM table to run stories for a group of players.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {/* Name */}
          <div className="space-y-1">
            <Label htmlFor="table-name">Name *</Label>
            <Input
              id="table-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Thornwood Campaign"
              maxLength={200}
              required
              aria-describedby={fieldErrors.name ? 'table-name-error' : undefined}
            />
            {fieldErrors.name && (
              <p id="table-name-error" className="text-sm text-destructive">
                {fieldErrors.name.join(' ')}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-1">
            <Label htmlFor="table-description">Description</Label>
            <Textarea
              id="table-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this table's theme or setting"
              rows={3}
            />
            {fieldErrors.description && (
              <p className="text-sm text-destructive">{fieldErrors.description.join(' ')}</p>
            )}
          </div>

          {/* Global errors */}
          {fieldErrors.non_field_errors && (
            <p className="text-sm text-destructive">{fieldErrors.non_field_errors.join(' ')}</p>
          )}
          {fieldErrors.detail && <p className="text-sm text-destructive">{fieldErrors.detail}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || isPending}>
              {isPending ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Table'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
