/**
 * JournalComposerDialog — write an entry from somewhere that is not the
 * Reading Room (#2160, rebuilt for #3941).
 *
 * The page has a desk that folds open above the stream; the sidebar's Journal
 * tab has this instead, because there is no stream there to fold it over. Both
 * render the same `JournalEntryFields`, so the two surfaces ask for exactly the
 * same things and neither can drift.
 *
 * Externally controlled (`open`/`onClose`), following the
 * `DramaticMomentTagDialog` pattern rather than owning its own trigger.
 * `initialTags` pre-seeds the chip list — a card action that opens the composer
 * "about this" attaches the tag without the player retyping it.
 *
 * No description under the title: interface copy on this page is plain and
 * unhelpful by ruling, and the two pills already say what the two journals are.
 */
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

import type { CreateJournalEntryRequest } from '../api';
import { useCreateJournalEntry } from '../queries';
import {
  EMPTY_ENTRY_FIELDS,
  isAboutUnresolved,
  type JournalEntryFieldsValue,
} from '../entryFields';
import { JournalEntryFields } from './JournalEntryFields';
// The dialog renders through a portal, outside the page's `.journals` root, and is
// opened from the sidebar on routes that never load `JournalsPage`. Importing the
// stylesheet here is what puts the `jr-*` rules in the document for those routes.
import '../journals.css';

interface JournalComposerDialogProps {
  open: boolean;
  onClose: () => void;
  /** Tags to pre-seed the chip list with when the dialog opens. */
  initialTags?: string[];
}

export function JournalComposerDialog({ open, onClose, initialTags }: JournalComposerDialogProps) {
  const [value, setValue] = useState<JournalEntryFieldsValue>(EMPTY_ENTRY_FIELDS);
  const createEntry = useCreateJournalEntry();

  // Reset (and re-seed tags) only on the closed->open transition, not on every
  // render while the dialog stays open — otherwise a parent passing a fresh
  // `initialTags` array literal each render would keep wiping what has been typed.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open && !wasOpen.current) {
      setValue({ ...EMPTY_ENTRY_FIELDS, tags: initialTags ?? [] });
    }
    wasOpen.current = open;
  }, [open, initialTags]);

  function handleSubmit() {
    if (!canSubmit) return;
    const payload: CreateJournalEntryRequest = {
      title: value.title.trim(),
      body: value.body,
      is_public: value.isPublic,
      tags: value.tags,
      about: value.about?.id ?? null,
    };
    // Omit the field entirely at the INHERIT default — never send a no-op override.
    if (value.posthumousOverride !== 'inherit') {
      payload.posthumous_override = value.posthumousOverride;
    }
    createEntry.mutate(payload, {
      onSuccess: () => {
        toast.success('Journal entry recorded.');
        onClose();
      },
      onError: (err: Error) => toast.error(err.message),
    });
  }

  // A name typed into About that has not resolved to anybody holds the button:
  // posting now would silently drop the subject the writer asked for.
  const canSubmit =
    value.title.trim().length > 0 &&
    value.body.trim().length > 0 &&
    !isAboutUnresolved(value) &&
    !createEntry.isPending;
  // Inline refusal rendering (#3412 T4) — a gate refusal (4xx `{detail}`, parsed into
  // `ApiError.message` by `readErrorDetail`/`createJournalEntry`) needs to stay readable
  // after the toast dismisses; the reason text IS the message, never rewritten here.
  const errorMessage =
    createEntry.isError && createEntry.error instanceof Error ? createEntry.error.message : null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => (isOpen ? undefined : onClose())}>
      <DialogContent className="journals max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Write a journal entry</DialogTitle>
        </DialogHeader>

        <JournalEntryFields value={value} onChange={setValue} showAfterDeath />

        {errorMessage ? (
          <p className="jr-sans m-0 text-sm text-destructive" data-testid="journal-composer-error">
            {errorMessage}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={createEntry.isPending}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {createEntry.isPending ? 'Posting…' : 'Post entry'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
