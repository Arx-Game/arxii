/**
 * JournalComposerDialog — write a new journal entry (#2160).
 *
 * Externally controlled (`open`/`onClose`), following the
 * `DramaticMomentTagDialog` pattern rather than owning its own trigger —
 * both the sidebar `JournalTab` and `JournalsPage` open it from their own
 * "Write" buttons. `initialTags` pre-seeds the chip list — Task 4's
 * card-action "post about this" flow opens the composer with a tag already
 * attached (e.g. a character or location name) so the entry gets tagged
 * without the player re-typing it.
 *
 * Tags are a chip list, never a comma-split string — the backend's
 * `tags` field is a `ListField` of exact strings
 * (`JournalEntryCreateSerializer`), so splitting on commas would silently
 * mangle any tag that legitimately contains one.
 */
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useCreateJournalEntry } from '../queries';

interface JournalComposerDialogProps {
  open: boolean;
  onClose: () => void;
  /** Tags to pre-seed the chip list with when the dialog opens. */
  initialTags?: string[];
}

export function JournalComposerDialog({ open, onClose, initialTags }: JournalComposerDialogProps) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [tagDraft, setTagDraft] = useState('');

  const createEntry = useCreateJournalEntry();

  // Reset (and re-seed tags) only on the closed->open transition, not on
  // every render while the dialog stays open — otherwise a parent that
  // passes a fresh `initialTags` array literal each render would keep
  // wiping out whatever the player has already typed.
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setTitle('');
      setBody('');
      setIsPublic(false);
      setTags(initialTags ?? []);
      setTagDraft('');
    }
    wasOpenRef.current = open;
  }, [open, initialTags]);

  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) onClose();
  }

  function addTagFromDraft() {
    const value = tagDraft.trim();
    if (!value) return;
    setTags((prev) => (prev.includes(value) ? prev : [...prev, value]));
    setTagDraft('');
  }

  function handleTagKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTagFromDraft();
    } else if (e.key === 'Backspace' && tagDraft === '' && tags.length > 0) {
      setTags((prev) => prev.slice(0, -1));
    }
  }

  function removeTag(tag: string) {
    setTags((prev) => prev.filter((t) => t !== tag));
  }

  function handleSubmit() {
    if (!title.trim() || !body.trim() || createEntry.isPending) return;
    createEntry.mutate(
      { title: title.trim(), body, is_public: isPublic, tags },
      {
        onSuccess: () => {
          toast.success('Journal entry recorded.');
          onClose();
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : 'Failed to post journal entry');
        },
      }
    );
  }

  const canSubmit = title.trim().length > 0 && body.trim().length > 0 && !createEntry.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Write a Journal Entry</DialogTitle>
          <DialogDescription>
            Private entries are visible only to you. Public entries can be read — and praised or
            retorted — by anyone.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="journal-title">Title</Label>
            <Input
              id="journal-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="A title for this entry"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="journal-body">Entry</Label>
            <Textarea
              id="journal-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="What's on your mind…"
              className="min-h-[160px]"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="journal-public">Public</Label>
            <Switch id="journal-public" checked={isPublic} onCheckedChange={setIsPublic} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="journal-tag-input">Tags</Label>
            {tags.length > 0 ? (
              <div className="flex flex-wrap gap-1.5" data-testid="journal-tag-list">
                {tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="gap-1 pr-1">
                    {tag}
                    <button
                      type="button"
                      onClick={() => removeTag(tag)}
                      aria-label={`Remove tag ${tag}`}
                      className="rounded-full px-1 hover:bg-secondary-foreground/10"
                    >
                      ×
                    </button>
                  </Badge>
                ))}
              </div>
            ) : null}
            <Input
              id="journal-tag-input"
              value={tagDraft}
              onChange={(e) => setTagDraft(e.target.value)}
              onKeyDown={handleTagKeyDown}
              onBlur={addTagFromDraft}
              placeholder="Type a tag and press Enter"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={createEntry.isPending}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {createEntry.isPending ? 'Posting…' : 'Post Entry'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
