import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTargetMenuSnapshot } from './useTargetMenuSnapshot';
import {
  fetchTargetMenu,
  targetMenuInputPageKey,
  targetMenuQueryPolicy,
  type TargetMenuCandidate,
  type TargetMenuEntry,
  TargetMenuFetchError,
  type TargetMenuTarget,
} from './targetMenuApi';

interface TargetMenuInputsProps {
  partition: string;
  actorId: number;
  target: TargetMenuTarget;
  entry: TargetMenuEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (kwargs: Record<string, unknown>) => boolean;
  submitting?: boolean;
}

function inputLabel(name: string): string {
  const labels: Record<string, string> = {
    recipient_persona_id: 'Give to',
    container_item_id: 'Put in',
    use_target: 'Use on',
    option_id: 'Choose an option',
  };
  return labels[name] ?? name;
}

function choiceErrorMessage(error: unknown, more = false): string {
  if (error instanceof TargetMenuFetchError && error.status === 429) {
    const wait = error.retryAfterSeconds;
    return wait === null
      ? 'Too many choice requests. Close and try again shortly.'
      : `Too many choice requests. Try again in ${Math.ceil(wait)} seconds.`;
  }
  return more
    ? 'Could not load more choices. Try again.'
    : 'Could not load current choices. Close and reopen to retry.';
}

function chooserPresentation(
  entry: TargetMenuEntry,
  inputs: TargetMenuEntry['inputs'],
  targetLabel?: string
) {
  if (entry.key === 'give') {
    return {
      title: 'Give item',
      description: 'Choose who to hand this to.',
      submitLabel: 'Give',
    };
  }
  if (entry.key === 'put_in') {
    return {
      title: 'Put item in…',
      description: targetLabel
        ? `${targetLabel} is already selected.`
        : 'Choose a container from your inventory.',
      submitLabel: 'Put In',
    };
  }
  if (entry.key === 'use_item') {
    const asksForTarget = inputs.some((input) => input.name === 'use_target');
    const asksForOption = inputs.some((input) => input.name === 'option_id');
    let description: string;
    if (asksForTarget) {
      description = 'Choose a target for this item.';
    } else if (asksForOption) {
      description = 'Choose an option for this item.';
    } else {
      description = 'Choose an available option before continuing.';
    }
    return { title: targetLabel ? `Use ${targetLabel}` : 'Use', description, submitLabel: 'Use' };
  }
  return {
    title: entry.label,
    description: 'Choose an available option before continuing.',
    submitLabel: 'Continue',
  };
}

/** Completes declared inputs using only complete, server-approved candidates. */
export function TargetMenuInputs({
  partition,
  actorId,
  target,
  entry,
  open,
  onOpenChange,
  onConfirm,
  submitting = false,
}: TargetMenuInputsProps) {
  const queryClient = useQueryClient();
  const [candidatePages, setCandidatePages] = useState<TargetMenuCandidate[]>([]);
  const [nextCandidateCursor, setNextCandidateCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const {
    data: refreshed,
    isLoading,
    error,
  } = useTargetMenuSnapshot(partition, actorId, target, open, entry.key);
  const activeEntry = Array.isArray(refreshed?.entries)
    ? (refreshed.entries.find((candidate) => candidate.key === entry.key) ?? null)
    : null;
  const requiredInputs = useMemo(
    () => activeEntry?.inputs.filter((input) => input.required) ?? [],
    [activeEntry]
  );
  const effectiveEntry = activeEntry ?? entry;
  const optionalInputs = activeEntry?.inputs.filter((input) => !input.required) ?? [];
  useEffect(() => {
    if (!activeEntry) return;
    setCandidatePages(activeEntry.candidates);
    setNextCandidateCursor(activeEntry.next_candidate_cursor ?? null);
    setLoadMoreError(null);
  }, [activeEntry]);
  const eligibleCandidates = useMemo(() => {
    const inputKeys: Record<string, string> = {
      recipient_persona_id: 'recipient_persona_id',
      container_item_id: 'container_item_id',
      use_target: 'use_target',
      option_id: 'option_id',
    };
    return (
      candidatePages.filter(
        (candidate) =>
          candidate.available &&
          requiredInputs.every((input) => {
            const key = inputKeys[input.name];
            return key !== undefined && key in candidate.kwargs;
          })
      ) ?? []
    );
  }, [candidatePages, requiredInputs]);
  const [selectedKey, setSelectedKey] = useState('');
  const [descriptor, setDescriptor] = useState('');
  const [blend, setBlend] = useState(false);
  const defaultCandidate = eligibleCandidates[0];
  const candidateKey = eligibleCandidates.some((candidate) => candidate.key === selectedKey)
    ? selectedKey
    : (defaultCandidate?.key ?? '');
  const selectedCandidate = useMemo(
    () => eligibleCandidates.find((candidate) => candidate.key === candidateKey),
    [candidateKey, eligibleCandidates]
  );
  const canConfirm = Boolean(activeEntry && selectedCandidate) && !isLoading && !error;

  async function loadMoreCandidates() {
    if (nextCandidateCursor === null || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const page = await queryClient.fetchQuery({
        queryKey: targetMenuInputPageKey(
          partition,
          actorId,
          target,
          entry.key,
          nextCandidateCursor
        ),
        queryFn: ({ signal }) =>
          fetchTargetMenu(actorId, target, signal, entry.key, nextCandidateCursor),
        ...targetMenuQueryPolicy,
      });
      const pageEntry = page.entries.find((candidate) => candidate.key === entry.key);
      if (!pageEntry) {
        setNextCandidateCursor(null);
        setLoadMoreError('No more choices are available. Close and reopen the menu.');
        return;
      }
      setCandidatePages((previous) => {
        const seen = new Set(previous.map((candidate) => candidate.key));
        return [
          ...previous,
          ...pageEntry.candidates.filter((candidate) => !seen.has(candidate.key)),
        ];
      });
      setNextCandidateCursor(pageEntry.next_candidate_cursor ?? null);
    } catch (loadError: unknown) {
      setLoadMoreError(choiceErrorMessage(loadError, true));
    } finally {
      setLoadingMore(false);
    }
  }

  function confirm() {
    if (!canConfirm || !selectedCandidate) return;
    const kwargs: Record<string, unknown> = {
      ...effectiveEntry.kwargs,
      ...selectedCandidate.kwargs,
    };
    if (optionalInputs.some((input) => input.name === 'descriptor')) kwargs.descriptor = descriptor;
    if (optionalInputs.some((input) => input.name === 'blend')) kwargs.blend = blend;
    const accepted = onConfirm(kwargs);
    if (accepted) onOpenChange(false);
  }

  let choiceLabel = 'Choose an option';
  if (requiredInputs.length === 1) choiceLabel = inputLabel(requiredInputs[0].name);
  if (requiredInputs.length > 1) {
    choiceLabel = `Choose ${requiredInputs.map((input) => inputLabel(input.name).toLowerCase()).join(' and ')}`;
  }

  const presentation = chooserPresentation(effectiveEntry, requiredInputs, refreshed?.label);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{presentation.title}</DialogTitle>
          <DialogDescription>{presentation.description}</DialogDescription>
          {isLoading ? <p role="status">Loading current choices…</p> : null}
          {error ? <p role="alert">{choiceErrorMessage(error)}</p> : null}
          {!isLoading && !error && !activeEntry ? (
            <p role="alert">These choices are no longer available. Close and reopen the menu.</p>
          ) : null}
        </DialogHeader>
        <div className="space-y-4">
          {requiredInputs.length > 0 ? (
            <div className="space-y-2">
              <fieldset className="max-h-60 space-y-2 overflow-y-auto" aria-label={choiceLabel}>
                <legend className="sr-only">{choiceLabel}</legend>
                {candidatePages
                  .filter(
                    (candidate) =>
                      !candidate.available ||
                      eligibleCandidates.some((eligible) => eligible.key === candidate.key)
                  )
                  .map((candidate) => {
                    const isEligible = eligibleCandidates.some(
                      (eligible) => eligible.key === candidate.key
                    );
                    const isSelected = isEligible && candidate.key === candidateKey;
                    return (
                      <label
                        key={candidate.key}
                        className={[
                          'flex w-full items-start gap-3 rounded-md border px-3 py-2 text-sm',
                          isEligible ? 'cursor-pointer' : 'cursor-not-allowed opacity-60',
                          isSelected ? 'border-primary bg-primary/5' : '',
                          isEligible && !isSelected ? 'hover:bg-muted/50' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                      >
                        <input
                          type="radio"
                          name={`target-menu-${entry.key}`}
                          value={candidate.key}
                          checked={isSelected}
                          disabled={!isEligible}
                          onChange={() => setSelectedKey(candidate.key)}
                          className="mt-0.5"
                        />
                        <span className="min-w-0">
                          <span className="block">{candidate.label}</span>
                          {!isEligible && candidate.reasons.length > 0 ? (
                            <span className="block text-xs text-muted-foreground">
                              {candidate.reasons.join('; ')}
                            </span>
                          ) : null}
                        </span>
                      </label>
                    );
                  })}
              </fieldset>
              {nextCandidateCursor !== null ? (
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={() => void loadMoreCandidates()}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading more choices…' : 'Load more choices'}
                </Button>
              ) : null}
              {loadMoreError ? (
                <p role="alert" className="text-sm text-destructive">
                  {loadMoreError}
                </p>
              ) : null}
            </div>
          ) : null}
          {optionalInputs.some((input) => input.name === 'descriptor') ? (
            <label className="block space-y-1 text-sm">
              <span>Appearance description (optional)</span>
              <input
                className="min-h-10 w-full rounded-md border bg-background px-3"
                value={descriptor}
                onChange={(event) => setDescriptor(event.target.value)}
              />
            </label>
          ) : null}
          {optionalInputs.some((input) => input.name === 'blend') ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={blend}
                onChange={(event) => setBlend(event.target.checked)}
              />
              Blend with existing appearance
            </label>
          ) : null}
          {!isLoading &&
          !error &&
          activeEntry &&
          requiredInputs.length > 0 &&
          eligibleCandidates.length === 0 ? (
            <p role="status" className="text-sm text-muted-foreground">
              {candidatePages
                .flatMap((candidate: TargetMenuCandidate) => candidate.reasons)
                .join(' ') ||
                (nextCandidateCursor !== null
                  ? 'More choices may be available.'
                  : 'No choices are available.')}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={confirm} disabled={!canConfirm || submitting}>
            {presentation.submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
