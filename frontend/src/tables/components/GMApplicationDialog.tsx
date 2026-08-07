/**
 * GMApplicationDialog — player applies to become a GM (#3041).
 *
 * Triggered from TablesListPage for authenticated non-GM users. Submits to
 * GMApplicationViewSet.create (any authenticated player). The endpoint is
 * create-only for non-staff callers, so there is no way to fetch back an
 * existing pending application; on success the parent tracks "submitted"
 * as local state for the rest of the session.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { bulletinErrorsFrom, type BulletinFieldErrors } from '../bulletinErrors';
import { FieldError, FormErrors } from './FieldError';
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useCreateGMApplication } from '../queries';

const MIN_LENGTH = 50;
const MAX_LENGTH = 10000;

interface GMApplicationDialogProps {
  children: React.ReactNode;
  onSuccess: () => void;
}

export function GMApplicationDialog({ children, onSuccess }: GMApplicationDialogProps) {
  const [open, setOpen] = useState(false);
  const [applicationText, setApplicationText] = useState('');
  const [fieldErrors, setFieldErrors] = useState<BulletinFieldErrors>({});

  const createMutation = useCreateGMApplication();

  function resetForm() {
    setApplicationText('');
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    createMutation.mutate(
      { application_text: applicationText.trim() },
      {
        onSuccess: () => {
          toast.success('GM application submitted');
          setOpen(false);
          onSuccess();
        },
        onError: (err: unknown) => {
          setFieldErrors(bulletinErrorsFrom(err));
        },
      }
    );
  }

  const trimmedLength = applicationText.trim().length;
  const isValid = trimmedLength >= MIN_LENGTH && trimmedLength <= MAX_LENGTH;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Apply to be a GM</DialogTitle>
          <DialogDescription>
            Tell us what you want to GM, which players you'd run for, and what stories you'd tell.
            Staff will review your application.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => handleSubmit(e)} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="gm-application-text">Application *</Label>
            <Textarea
              id="gm-application-text"
              value={applicationText}
              onChange={(e) => setApplicationText(e.target.value)}
              placeholder="What do you want to GM? Who would you run for? What stories would you tell?"
              rows={6}
              maxLength={MAX_LENGTH}
              required
              aria-describedby={
                fieldErrors.application_text ? 'gm-application-text-error' : undefined
              }
            />
            <p className="text-xs text-muted-foreground">
              {trimmedLength} / {MIN_LENGTH} characters minimum
            </p>
            <FieldError
              errors={fieldErrors}
              field="application_text"
              id="gm-application-text-error"
            />
          </div>

          <FormErrors errors={fieldErrors} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || createMutation.isPending}>
              {createMutation.isPending ? 'Submitting…' : 'Submit Application'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
