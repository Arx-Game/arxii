/**
 * ChangeMyGMDialog — combined 2-step dialog for player story GM reassignment.
 *
 * Step 1 (only if story has a primary_table): Confirm withdrawal from current GM.
 * Step 2: Offer to a new GM (GM picker autocomplete + optional message).
 *
 * Usage:
 *   <ChangeMyGMDialog story={story} />
 *
 * The dialog button label adapts:
 *   - Story has primary_table → "Change my GM"
 *   - Story has primary_table=null → "Offer to a GM"
 */

import { useState, useCallback } from 'react';
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { useDetachStoryFromTable, useGMProfiles, useOfferStoryToGM } from '../queries';
import type { GMProfile, Story } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  gm_profile_id?: string[];
  message?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChangeMyGMDialogProps {
  story: Story;
}

// ---------------------------------------------------------------------------
// Step 1: Withdraw confirmation
// ---------------------------------------------------------------------------

interface WithdrawStepProps {
  story: Story;
  onSuccess: () => void;
  onCancel: () => void;
}

function WithdrawStep({ story, onSuccess, onCancel }: WithdrawStepProps) {
  const detach = useDetachStoryFromTable();

  function handleWithdraw() {
    detach.mutate(story.id, {
      onSuccess: () => {
        toast.success('Story withdrawn from current GM');
        onSuccess();
      },
      onError: () => {
        toast.error('Failed to withdraw story. Please try again.');
      },
    });
  }

  // The current GM name is in story.active_gms (array of GMProfile objects).
  // We show the first one's username if available.
  const firstGM = story.active_gms[0] as { account_username?: string; id?: number } | undefined;
  const currentGMName =
    firstGM?.account_username ?? (firstGM?.id != null ? `GM #${firstGM.id}` : 'the current GM');

  return (
    <>
      <DialogHeader>
        <DialogTitle>Withdraw from current GM?</DialogTitle>
        <DialogDescription>
          Withdraw &quot;{story.title}&quot; from {currentGMName}? Your story will enter
          &quot;seeking GM&quot; state. Story history and progress are preserved.
        </DialogDescription>
      </DialogHeader>

      <DialogFooter className="mt-6">
        <Button type="button" variant="outline" onClick={onCancel} disabled={detach.isPending}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="destructive"
          onClick={handleWithdraw}
          disabled={detach.isPending}
        >
          {detach.isPending ? 'Withdrawing…' : 'Withdraw'}
        </Button>
      </DialogFooter>
    </>
  );
}

// ---------------------------------------------------------------------------
// GM search result row
// ---------------------------------------------------------------------------

interface GMOptionProps {
  gm: GMProfile;
  selected: boolean;
  onSelect: (gm: GMProfile) => void;
}

function GMOption({ gm, selected, onSelect }: GMOptionProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(gm)}
      className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
        selected ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
      }`}
      data-testid={`gm-option-${gm.id}`}
    >
      <span className="font-medium">{gm.account_username}</span>
      <span className="ml-2 text-xs capitalize opacity-70">{gm.level}</span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Offer to new GM
// ---------------------------------------------------------------------------

interface OfferStepProps {
  story: Story;
  onSuccess: (gmName: string) => void;
  onCancel: () => void;
}

function OfferStep({ story, onSuccess, onCancel }: OfferStepProps) {
  const [search, setSearch] = useState('');
  const [selectedGM, setSelectedGM] = useState<{
    id: number;
    account_username: string;
  } | null>(null);
  const [message, setMessage] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const offerMutation = useOfferStoryToGM();

  // Debounce search — only query when 2+ chars to avoid hammering the API.
  const { data: gmData, isLoading: gmLoading } = useGMProfiles(
    search.length >= 2 ? { search, page_size: 10 } : undefined
  );
  const gmOptions = (gmData?.results ?? []) as GMProfile[];

  const handleGMSelect = useCallback((gm: GMProfile) => {
    setSelectedGM(gm);
    setSearch(gm.account_username);
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedGM) return;
    setFieldErrors({});

    offerMutation.mutate(
      {
        storyId: story.id,
        gm_profile_id: selectedGM.id,
        message: message.trim() || undefined,
      },
      {
        onSuccess: () => {
          onSuccess(selectedGM.account_username);
        },
        onError: (err: unknown) => {
          if (err && typeof err === 'object') {
            const asError = err as Error;
            // Try to extract DRF field errors from response body.
            void Promise.resolve()
              .then(async () => {
                const fetchErr = err as { response?: Response };
                if (fetchErr.response) {
                  const data: unknown = await fetchErr.response.json();
                  if (data && typeof data === 'object') {
                    setFieldErrors(data as DRFFieldErrors);
                    return;
                  }
                }
                toast.error(asError.message ?? 'Failed to send offer. Please try again.');
              })
              .catch(() => {
                toast.error('Failed to send offer. Please try again.');
              });
          } else {
            toast.error('Failed to send offer. Please try again.');
          }
        },
      }
    );
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';
  const showDropdown = search.length >= 2 && selectedGM === null;
  // Capture in a local alias so TypeScript doesn't narrow it to `never`
  // inside the `showDropdown &&` JSX guard (which implies selectedGM===null).
  const currentSelectedGM = selectedGM;

  return (
    <form onSubmit={handleSubmit}>
      <DialogHeader>
        <DialogTitle>Offer to a GM</DialogTitle>
        <DialogDescription>
          Choose a GM to offer &quot;{story.title}&quot; to. They can accept or decline.
        </DialogDescription>
      </DialogHeader>

      {/* Global error banner */}
      {(nonFieldErrors.length > 0 || detailError) && (
        <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {detailError && <p>{detailError}</p>}
          {nonFieldErrors.map((msg, i) => (
            <p key={i}>{msg}</p>
          ))}
        </div>
      )}

      <div className="mt-4 grid gap-4">
        {/* GM picker */}
        <div className="space-y-1.5">
          <Label htmlFor="gm-search">GM</Label>
          <div className="relative">
            <Input
              id="gm-search"
              placeholder="Type a GM username to search…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                if (selectedGM && e.target.value !== selectedGM.account_username) {
                  setSelectedGM(null);
                }
              }}
              autoComplete="off"
              data-testid="gm-search-input"
            />
            {showDropdown && (
              <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md">
                {gmLoading && <p className="px-3 py-2 text-sm text-muted-foreground">Searching…</p>}
                {!gmLoading && gmOptions.length === 0 && (
                  <p
                    className="px-3 py-2 text-sm text-muted-foreground"
                    data-testid="gm-no-results"
                  >
                    No GMs found.
                  </p>
                )}
                {!gmLoading &&
                  gmOptions.map((gm: GMProfile) => (
                    <GMOption
                      key={gm.id}
                      gm={gm}
                      selected={currentSelectedGM?.id === gm.id}
                      onSelect={handleGMSelect}
                    />
                  ))}
              </div>
            )}
          </div>
          {selectedGM && (
            <p className="text-xs text-muted-foreground" data-testid="gm-selected-confirmation">
              Selected: <span className="font-medium">{selectedGM.account_username}</span>
            </p>
          )}
          {fieldErrors.gm_profile_id && fieldErrors.gm_profile_id.length > 0 && (
            <p className="text-xs text-destructive">{fieldErrors.gm_profile_id.join(' ')}</p>
          )}
        </div>

        {/* Optional message */}
        <div className="space-y-1.5">
          <Label htmlFor="offer-message">
            Message <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Textarea
            id="offer-message"
            placeholder="Tell the GM about your story, your play style, or what you're hoping for…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            data-testid="offer-message-input"
          />
          {fieldErrors.message && fieldErrors.message.length > 0 && (
            <p className="text-xs text-destructive">{fieldErrors.message.join(' ')}</p>
          )}
        </div>
      </div>

      <DialogFooter className="mt-6">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={offerMutation.isPending}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={offerMutation.isPending || !selectedGM}
          data-testid="offer-submit-button"
        >
          {offerMutation.isPending ? 'Sending…' : 'Send Offer'}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Main dialog
// ---------------------------------------------------------------------------

type DialogStep = 'withdraw' | 'offer';

export function ChangeMyGMDialog({ story }: ChangeMyGMDialogProps) {
  const [open, setOpen] = useState(false);
  // If story has a primary_table, start at withdraw step; else skip to offer step.
  const initialStep: DialogStep = story.primary_table != null ? 'withdraw' : 'offer';
  const [step, setStep] = useState<DialogStep>(initialStep);

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      // Reset to the correct initial step each time the dialog opens.
      setStep(story.primary_table != null ? 'withdraw' : 'offer');
    }
  }

  function handleWithdrawSuccess() {
    setStep('offer');
  }

  function handleOfferSuccess(gmName: string) {
    setOpen(false);
    toast.success(`Offer sent to ${gmName}`);
  }

  function handleCancel() {
    setOpen(false);
  }

  const buttonLabel = story.primary_table != null ? 'Change my GM' : 'Offer to a GM';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="change-gm-button">
          {buttonLabel}
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        {step === 'withdraw' ? (
          <WithdrawStep story={story} onSuccess={handleWithdrawSuccess} onCancel={handleCancel} />
        ) : (
          <OfferStep story={story} onSuccess={handleOfferSuccess} onCancel={handleCancel} />
        )}
      </DialogContent>
    </Dialog>
  );
}
