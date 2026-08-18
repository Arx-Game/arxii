/**
 * AuthorSecretDialog — staff create/edit dialog for a character's authored secrets (#3266).
 *
 * Mirrors the mutation + inline-error shape of SpreadTaleDialog (`useMutation` +
 * `mutation.isError` rendered as destructive text) rather than OriginStoryEditorDialog's
 * save-on-change pattern, since this form has a real submit step and can fail validation
 * server-side (e.g. an empty `content`).
 *
 * Create mode (no `secret` prop): posts a new GM-authored secret about `subjectId`.
 * Edit mode (`secret` supplied): patches its editable fields. `subject_sheet` and
 * `provenance` are fixed server-side and never sent from edit mode.
 */

import { type ReactNode, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import {
  useCreateAuthoredSecretMutation,
  useSecretCategoriesQuery,
  useUpdateAuthoredSecretMutation,
} from '../queries';
import type { AuthoredSecret } from '../types';

// PLACEHOLDER labels — mirrors `SecretLevel` in `world/secrets/constants.py` (also marked
// PLACEHOLDER there pending a workshop pass with Apostate). The frontend has no generated
// enum-label mapping to read from, so these value/label pairs are hand-kept in sync.
const LEVEL_OPTIONS = [
  { value: '1', label: 'Uncommon Knowledge' },
  { value: '2', label: 'Whispers' },
  { value: '3', label: 'Carefully Kept' },
  { value: '4', label: 'Dangerous Secret' },
];

const NO_CATEGORY = 'unknown';

interface AuthorSecretDialogProps {
  subjectId: number;
  /** Present in edit mode; omitted for create. */
  secret?: AuthoredSecret;
  trigger: ReactNode;
}

export function AuthorSecretDialog({ subjectId, secret, trigger }: AuthorSecretDialogProps) {
  const isEdit = secret != null;
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState(secret?.content ?? '');
  const [level, setLevel] = useState(String(secret?.level ?? 1));
  const [category, setCategory] = useState(
    secret?.category != null ? String(secret.category) : NO_CATEGORY
  );
  const [consequences, setConsequences] = useState(secret?.consequences ?? '');
  const [subjectAware, setSubjectAware] = useState(secret?.subject_aware ?? true);

  const { data: categories } = useSecretCategoriesQuery();
  const createMutation = useCreateAuthoredSecretMutation();
  const updateMutation = useUpdateAuthoredSecretMutation();
  const mutation = isEdit ? updateMutation : createMutation;

  const resetToSource = () => {
    setContent(secret?.content ?? '');
    setLevel(String(secret?.level ?? 1));
    setCategory(secret?.category != null ? String(secret.category) : NO_CATEGORY);
    setConsequences(secret?.consequences ?? '');
    setSubjectAware(secret?.subject_aware ?? true);
  };

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) resetToSource();
  };

  const handleSubmit = () => {
    const payload = {
      content,
      level: Number(level),
      category: category === NO_CATEGORY ? null : Number(category),
      consequences,
      subject_aware: subjectAware,
    };
    if (isEdit) {
      updateMutation.mutate({ id: secret.id, payload }, { onSuccess: () => setOpen(false) });
    } else {
      createMutation.mutate(
        { subject_sheet: subjectId, ...payload },
        { onSuccess: () => setOpen(false) }
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit secret' : 'Author secret'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="secret-content">Content</Label>
            <Textarea
              id="secret-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={4}
              className="resize-y"
              placeholder="The secret itself, as narrated."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="secret-level">Level</Label>
            <Select value={level} onValueChange={setLevel}>
              <SelectTrigger id="secret-level" aria-label="Level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVEL_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="secret-category">Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger id="secret-category" aria-label="Category">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_CATEGORY}>Unknown</SelectItem>
                {(categories ?? []).map((option) => (
                  <SelectItem key={option.id} value={String(option.id)}>
                    {option.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="secret-consequences">Consequences</Label>
            <Textarea
              id="secret-consequences"
              value={consequences}
              onChange={(e) => setConsequences(e.target.value)}
              rows={3}
              className="resize-y"
              placeholder="What happens if it surfaces."
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              id="secret-subject-aware"
              type="checkbox"
              checked={subjectAware}
              onChange={(e) => setSubjectAware(e.target.checked)}
              className="h-4 w-4 rounded border-input"
            />
            <Label htmlFor="secret-subject-aware" className="font-normal">
              Subject starts aware of this secret about themselves
            </Label>
          </div>
          {mutation.isError && (
            <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            data-testid="author-secret-submit"
            onClick={handleSubmit}
            disabled={content.trim().length === 0 || mutation.isPending}
          >
            {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Author secret'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
