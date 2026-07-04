/**
 * PlayerBoundaryFormDialog — create or edit a PlayerBoundary (#1771).
 *
 * kind = HARD_LINE requires a ContentTheme and is always PRIVATE (enforced
 * client-side to match the backend's `PlayerBoundarySerializer.validate()`
 * invariant — ADR-0033). kind = ADVISORY allows no theme and optional
 * sharing (public / private / specific characters).
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
import { useContentThemes, useCreatePlayerBoundary, useUpdatePlayerBoundary } from '../queries';
import type { PlayerBoundary, PlayerBoundaryKindEnum, VisibilityModeEnum } from '../types';
import type { Option } from '@/shared/types';

function tenureOptionsFromIds(ids: number[] | undefined): Option<number>[] {
  return (ids ?? []).map((id) => ({ value: id, label: String(id) }));
}

interface DRFFieldErrors {
  theme?: string[];
  detail?: string[];
  visibility_mode?: string[];
  non_field_errors?: string[];
  detail_message?: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When provided, the dialog edits this boundary instead of creating one. */
  boundary?: PlayerBoundary;
  onSuccess?: (boundary: PlayerBoundary) => void;
}

export function PlayerBoundaryFormDialog({ open, onOpenChange, boundary, onSuccess }: Props) {
  const isEdit = boundary !== undefined;

  const [kind, setKind] = useState<PlayerBoundaryKindEnum>(boundary?.kind ?? 'advisory');
  const [theme, setTheme] = useState<string>(boundary?.theme != null ? String(boundary.theme) : '');
  const [detail, setDetail] = useState(boundary?.detail ?? '');
  const [visibilityMode, setVisibilityMode] = useState<VisibilityModeEnum>(
    boundary?.visibility_mode ?? 'private'
  );
  const [visibleToTenures, setVisibleToTenures] = useState<Option<number>[]>(
    tenureOptionsFromIds(boundary?.visible_to_tenures)
  );
  const [localError, setLocalError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const { data: themes } = useContentThemes();
  const createMutation = useCreatePlayerBoundary();
  const updateMutation = useUpdatePlayerBoundary();
  const isPending = createMutation.isPending || updateMutation.isPending;

  const isHardLine = kind === 'hard_line';
  const effectiveVisibility: VisibilityModeEnum = isHardLine ? 'private' : visibilityMode;

  function resetForm() {
    setKind(boundary?.kind ?? 'advisory');
    setTheme(boundary?.theme != null ? String(boundary.theme) : '');
    setDetail(boundary?.detail ?? '');
    setVisibilityMode(boundary?.visibility_mode ?? 'private');
    setVisibleToTenures(tenureOptionsFromIds(boundary?.visible_to_tenures));
    setLocalError(null);
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    onOpenChange(next);
  }

  function handleKindChange(value: string) {
    const nextKind = value as PlayerBoundaryKindEnum;
    setKind(nextKind);
    if (nextKind === 'hard_line') {
      setVisibilityMode('private');
    }
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

    if (kind === 'hard_line' && theme === '') {
      setLocalError('Theme is required for a hard line.');
      return;
    }

    const body = {
      kind,
      theme: theme !== '' ? Number(theme) : null,
      detail: detail.trim(),
      visibility_mode: effectiveVisibility,
      visible_to_tenures:
        effectiveVisibility === 'characters' ? visibleToTenures.map((t) => t.value) : [],
    };

    if (isEdit && boundary) {
      updateMutation.mutate(
        { id: boundary.id, body },
        {
          onSuccess: (updated: PlayerBoundary) => {
            toast.success('Boundary updated');
            handleOpenChange(false);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(body, {
        onSuccess: (created: PlayerBoundary) => {
          toast.success('Boundary saved');
          handleOpenChange(false);
          onSuccess?.(created);
        },
        onError: handleError,
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit boundary' : 'Add a content boundary'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="boundary-kind">Kind</Label>
            <Select value={kind} onValueChange={handleKindChange}>
              <SelectTrigger id="boundary-kind">
                <SelectValue placeholder="Kind" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="hard_line">Hard line (auto-blocked, always private)</SelectItem>
                <SelectItem value="advisory">Advisory (communicated, shareable)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="boundary-theme">Content theme{isHardLine ? ' (required)' : ''}</Label>
            <Select value={theme} onValueChange={setTheme}>
              <SelectTrigger id="boundary-theme">
                <SelectValue placeholder="Select a theme" />
              </SelectTrigger>
              <SelectContent>
                {themes?.results.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="boundary-detail">Detail</Label>
            <Textarea
              id="boundary-detail"
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
              placeholder={
                isHardLine
                  ? 'Staff/audit-only nuance — never shown to anyone else.'
                  : 'What should scene partners know?'
              }
              rows={3}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="boundary-visibility">Who can see this</Label>
            <Select
              value={effectiveVisibility}
              onValueChange={(v) => setVisibilityMode(v as VisibilityModeEnum)}
              disabled={isHardLine}
            >
              <SelectTrigger id="boundary-visibility">
                <SelectValue placeholder="Visibility" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Private (just you)</SelectItem>
                <SelectItem value="public">Public (anyone)</SelectItem>
                <SelectItem value="characters">Specific characters</SelectItem>
              </SelectContent>
            </Select>
            {isHardLine && (
              <p className="text-xs text-muted-foreground">
                Hard lines are always private and cannot be shared.
              </p>
            )}
            {!isHardLine && effectiveVisibility === 'characters' && (
              <TenureMultiSearch
                value={visibleToTenures}
                onChange={setVisibleToTenures}
                label="Shared with"
              />
            )}
          </div>

          {localError && <p className="text-sm text-destructive">{localError}</p>}
          {fieldErrors.theme && <p className="text-sm text-destructive">{fieldErrors.theme[0]}</p>}
          {fieldErrors.detail && (
            <p className="text-sm text-destructive">{fieldErrors.detail[0]}</p>
          )}
          {fieldErrors.non_field_errors && (
            <p className="text-sm text-destructive">{fieldErrors.non_field_errors[0]}</p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isEdit ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
