/**
 * TreasuredSubjectFormDialog — flag (create/edit) a TreasuredSubject for one
 * of the player's own tenures (#1771). `subject_label` carries the
 * human-readable identity for every kind (freeform for CUSTOM /
 * CAMPAIGN_TRACK / LOCATION, flavor text for the FK-backed kinds) — the
 * typed FK pickers (subject_sheet / subject_item / subject_society /
 * subject_organization) are a follow-on enhancement; this form covers the
 * label + detail + sharing surface every kind needs.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { TenureMultiSearch } from '@/components/TenureMultiSearch';
import { useCreateTreasuredSubject, useUpdateTreasuredSubject } from '../queries';
import type { SubjectKindEnum, TreasuredSubject, VisibilityModeEnum } from '../types';
import type { Option } from '@/shared/types';

function tenureOptionsFromIds(ids: number[] | undefined): Option<number>[] {
  return (ids ?? []).map((id) => ({ value: id, label: String(id) }));
}

const SUBJECT_KIND_LABELS: Record<SubjectKindEnum, string> = {
  personal_jeopardy: 'Personal jeopardy',
  npc_fate: 'NPC fate',
  location: 'Location',
  faction: 'Faction relationship',
  item: 'Item',
  campaign_track: 'Campaign track',
  custom: 'Custom',
};

interface DRFFieldErrors {
  subject_label?: string[];
  detail?: string[];
  non_field_errors?: string[];
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tenureId: number;
  /** When provided, the dialog edits this treasured subject instead of creating one. */
  subject?: TreasuredSubject;
  onSuccess?: (subject: TreasuredSubject) => void;
}

export function TreasuredSubjectFormDialog({
  open,
  onOpenChange,
  tenureId,
  subject,
  onSuccess,
}: Props) {
  const isEdit = subject !== undefined;

  const [subjectKind, setSubjectKind] = useState<SubjectKindEnum>(
    subject?.subject_kind ?? 'custom'
  );
  const [subjectLabel, setSubjectLabel] = useState(subject?.subject_label ?? '');
  const [detail, setDetail] = useState(subject?.detail ?? '');
  const [visibilityMode, setVisibilityMode] = useState<VisibilityModeEnum>(
    subject?.visibility_mode ?? 'private'
  );
  const [visibleToTenures, setVisibleToTenures] = useState<Option<number>[]>(
    tenureOptionsFromIds(subject?.visible_to_tenures)
  );
  const [localError, setLocalError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateTreasuredSubject();
  const updateMutation = useUpdateTreasuredSubject();
  const isPending = createMutation.isPending || updateMutation.isPending;

  function resetForm() {
    setSubjectKind(subject?.subject_kind ?? 'custom');
    setSubjectLabel(subject?.subject_label ?? '');
    setDetail(subject?.detail ?? '');
    setVisibilityMode(subject?.visibility_mode ?? 'private');
    setVisibleToTenures(tenureOptionsFromIds(subject?.visible_to_tenures));
    setLocalError(null);
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    onOpenChange(next);
  }

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') setFieldErrors(data as DRFFieldErrors);
          })
          .catch(() => toast.error('An error occurred. Please try again.'));
        return;
      }
    }
    toast.error(err instanceof Error ? err.message : 'An error occurred. Please try again.');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);
    setFieldErrors({});

    if (subjectLabel.trim() === '') {
      setLocalError('A label is required so you can recognize this later.');
      return;
    }

    const sharedTenures =
      visibilityMode === 'characters' ? visibleToTenures.map((t) => t.value) : [];

    if (isEdit && subject) {
      updateMutation.mutate(
        {
          id: subject.id,
          tenureId,
          body: {
            subject_kind: subjectKind,
            subject_label: subjectLabel.trim(),
            detail: detail.trim(),
            visibility_mode: visibilityMode,
            visible_to_tenures: sharedTenures,
          },
        },
        {
          onSuccess: ({ updated }) => {
            toast.success('Treasured subject updated');
            handleOpenChange(false);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(
        {
          owner: tenureId,
          subject_kind: subjectKind,
          subject_label: subjectLabel.trim(),
          detail: detail.trim(),
          visibility_mode: visibilityMode,
          visible_to_tenures: sharedTenures,
        },
        {
          onSuccess: (created) => {
            toast.success('Treasured subject flagged');
            handleOpenChange(false);
            onSuccess?.(created);
          },
          onError: handleError,
        }
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? 'Edit treasured subject' : 'Flag a treasured subject'}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="subject-kind">Kind</Label>
            <Select value={subjectKind} onValueChange={(v) => setSubjectKind(v as SubjectKindEnum)}>
              <SelectTrigger id="subject-kind">
                <SelectValue placeholder="Kind" />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(SUBJECT_KIND_LABELS) as SubjectKindEnum[]).map((kind) => (
                  <SelectItem key={kind} value={kind}>
                    {SUBJECT_KIND_LABELS[kind]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="subject-label">Label</Label>
            <Input
              id="subject-label"
              value={subjectLabel}
              onChange={(e) => setSubjectLabel(e.target.value)}
              placeholder="e.g. Captain Elara, the old windmill, my house seat"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="subject-detail">Why this matters (optional, may be shared)</Label>
            <Textarea
              id="subject-detail"
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
              rows={3}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="subject-visibility">Who can see this</Label>
            <Select
              value={visibilityMode}
              onValueChange={(v) => setVisibilityMode(v as VisibilityModeEnum)}
            >
              <SelectTrigger id="subject-visibility">
                <SelectValue placeholder="Visibility" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Private (just you)</SelectItem>
                <SelectItem value="public">Public (anyone)</SelectItem>
                <SelectItem value="characters">Specific characters</SelectItem>
              </SelectContent>
            </Select>
            {visibilityMode === 'characters' && (
              <TenureMultiSearch
                value={visibleToTenures}
                onChange={setVisibleToTenures}
                label="Shared with"
              />
            )}
          </div>

          {localError && <p className="text-sm text-destructive">{localError}</p>}
          {fieldErrors.subject_label && (
            <p className="text-sm text-destructive">{fieldErrors.subject_label[0]}</p>
          )}
          {fieldErrors.non_field_errors && (
            <p className="text-sm text-destructive">{fieldErrors.non_field_errors[0]}</p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isEdit ? 'Save' : 'Flag it'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
