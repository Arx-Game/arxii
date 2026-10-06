import { Fragment, type ReactElement, useEffect, useMemo, useRef, useState } from 'react';
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
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { useDispatchPlayerAction } from '@/combat/queries';
import { useAppSelector } from '@/store/hooks';
import { TargetMenuInputs } from './TargetMenuInputs';
import { isDispatchFailure, type ActionRef } from '@/combat/types';
import { useTargetMenuSnapshot } from './useTargetMenuSnapshot';
import { TargetMenuFetchError, type TargetMenuEntry, type TargetMenuTarget } from './targetMenuApi';

interface TargetMenuProps {
  partition: string;
  actorId: number | null;
  target: TargetMenuTarget;
  children: ReactElement;
}

function fetchErrorMessage(error: unknown): string {
  if (!(error instanceof TargetMenuFetchError))
    return 'Actions could not be loaded. Close and reopen to retry.';
  if (error.status === 429) {
    const wait = error.retryAfterSeconds;
    return wait === null
      ? 'Too many action-menu requests. Close and try again shortly.'
      : `Too many action-menu requests. Try again in ${Math.ceil(wait)} seconds.`;
  }
  return 'Actions could not be loaded. Close and reopen to retry.';
}

function getEntryLabel(entry: TargetMenuEntry): string {
  const opensChooser = entry.inputs.some((input) => input.required);
  if (!opensChooser || /[.…]$/.test(entry.label)) return entry.label;
  return `${entry.label}…`;
}

function MenuEntries({
  actorId,
  entries,
  onChooseInputs,
  onConfirmAuthored,
  actorIsCurrent,
  targetIsCurrent,
}: {
  actorId: number;
  entries: TargetMenuEntry[];
  onChooseInputs: (entry: TargetMenuEntry) => void;
  onConfirmAuthored: (entry: TargetMenuEntry) => void;
  actorIsCurrent: boolean;
  targetIsCurrent: boolean;
}) {
  const { mutateAsync, isPending } = useDispatchPlayerAction(actorId);
  return (
    <>
      {entries.map((entry) => (
        <ContextMenuItem
          key={entry.key}
          disabled={!entry.available || isPending}
          onSelect={() => {
            if (!entry.available || !actorIsCurrent || !targetIsCurrent) return;
            if (entry.group === 'authored') {
              if (entry.action !== null) onConfirmAuthored(entry);
              return;
            }
            if (entry.inputs.some((input) => input.required)) {
              onChooseInputs(entry);
              return;
            }
            void mutateAsync({
              ref: entry.ref as ActionRef,
              kwargs: entry.kwargs,
            })
              .then((result) => {
                if (isDispatchFailure(result)) {
                  toast.error(result.message ?? `Couldn't ${entry.label.toLowerCase()}.`);
                } else if (!result.deferred) {
                  toast.success(result.message ?? `${entry.label} complete.`);
                }
              })
              .catch(() => toast.error(`Couldn't ${entry.label.toLowerCase()}.`));
          }}
          aria-describedby={entry.reasons.length > 0 ? `${entry.key}-reason` : undefined}
        >
          <span className="flex min-w-0 flex-col">
            <span>{getEntryLabel(entry)}</span>
            {!entry.available && entry.reasons.length > 0 ? (
              <span id={`${entry.key}-reason`} className="text-xs text-muted-foreground">
                {entry.reasons.join(' · ')}
              </span>
            ) : null}
          </span>
        </ContextMenuItem>
      ))}
    </>
  );
}

/** Server-composed actions for a target, fetched once each time the menu opens. */
export function TargetMenu({ partition, actorId, target, children }: TargetMenuProps) {
  const [open, setOpen] = useState(false);
  const activeCharacterId = useAppSelector((state) => {
    const active = state.game.active;
    return active === null
      ? null
      : (state.auth.account?.available_characters.find((character) => character.name === active)
          ?.id ?? null);
  });
  const [inputEntry, setInputEntry] = useState<TargetMenuEntry | null>(null);
  const [authoredEntry, setAuthoredEntry] = useState<TargetMenuEntry | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const { mutateAsync } = useDispatchPlayerAction(actorId ?? 0);
  const openingIdentity = useMemo(
    () =>
      JSON.stringify([
        partition,
        actorId,
        target.kind,
        target.target_id,
        target.owner_persona_id ?? null,
        target.container_item_id ?? null,
      ]),
    [actorId, partition, target]
  );
  const currentIdentity = JSON.stringify([
    partition,
    actorId,
    target.kind,
    target.target_id,
    target.owner_persona_id ?? null,
    target.container_item_id ?? null,
  ]);
  const chooserIdentity = useRef<string | null>(null);
  useEffect(() => {
    if (inputEntry === null && authoredEntry === null) chooserIdentity.current = null;
  }, [authoredEntry, inputEntry]);
  useEffect(() => {
    if (inputEntry !== null && chooserIdentity.current !== openingIdentity) {
      setInputEntry(null);
      setDispatching(false);
    }
    if (authoredEntry !== null && chooserIdentity.current !== openingIdentity) {
      setAuthoredEntry(null);
      setDispatching(false);
    }
  }, [authoredEntry, inputEntry, openingIdentity]);
  const { data, error, isLoading } = useTargetMenuSnapshot(partition, actorId, target, open);

  return (
    <>
      <ContextMenu onOpenChange={setOpen}>
        <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
        <ContextMenuContent className="max-h-[min(32rem,80vh)] min-w-56 overflow-y-auto">
          {!data && isLoading ? <ContextMenuLabel>Loading actions…</ContextMenuLabel> : null}
          {!data && error ? (
            <ContextMenuLabel className="text-muted-foreground">
              {fetchErrorMessage(error)}
            </ContextMenuLabel>
          ) : null}
          {data ? (
            <ContextMenuLabel
              className="text-xs font-normal text-muted-foreground"
              data-testid="target-menu-label"
            >
              {data.label}
            </ContextMenuLabel>
          ) : null}
          {data && data.entries.length === 0 ? (
            <ContextMenuLabel className="text-muted-foreground">
              No actions available.
            </ContextMenuLabel>
          ) : null}
          {data?.groups.map((group, index) => {
            const entries = data.entries.filter((entry) => entry.group === group.key);
            if (entries.length === 0) return null;
            return (
              <Fragment key={group.key}>
                {index > 0 ? <ContextMenuSeparator /> : null}
                <MenuEntries
                  actorId={data.actor_id}
                  entries={entries}
                  actorIsCurrent={activeCharacterId === actorId}
                  targetIsCurrent={openingIdentity === currentIdentity}
                  onConfirmAuthored={(entry) => {
                    chooserIdentity.current = openingIdentity;
                    setAuthoredEntry(entry);
                  }}
                  onChooseInputs={(entry) => {
                    chooserIdentity.current = openingIdentity;
                    setInputEntry(entry);
                  }}
                />
              </Fragment>
            );
          })}
        </ContextMenuContent>
      </ContextMenu>
      {authoredEntry && actorId !== null ? (
        <Dialog
          open
          onOpenChange={(next) => {
            if (!next) setAuthoredEntry(null);
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{authoredEntry.label}</DialogTitle>
              <DialogDescription>
                {authoredEntry.action?.description ||
                  'Review the possible outcomes before continuing.'}
              </DialogDescription>
              {authoredEntry.action?.difficulty ? (
                <p className="text-sm">
                  <span className="font-medium">Difficulty:</span> {authoredEntry.action.difficulty}
                </p>
              ) : null}
              {authoredEntry.action?.prerequisite_reasons.length ? (
                <p className="text-sm">
                  <span className="font-medium">Requirement:</span>{' '}
                  {authoredEntry.action.prerequisite_reasons.join(' · ')}
                </p>
              ) : null}
            </DialogHeader>
            {authoredEntry.risk ? (
              <div className="space-y-2 text-sm">
                {authoredEntry.risk.known ? (
                  <>
                    <p>
                      {authoredEntry.risk.character_loss_possible
                        ? 'Character loss is possible.'
                        : 'No character-loss outcome is listed.'}
                    </p>
                    <ul className="list-disc space-y-1 pl-5">
                      {authoredEntry.risk.outcomes.map((outcome, index) => (
                        <li key={`${outcome.stage}-${outcome.tier}-${index}`}>
                          {outcome.stage}: {outcome.tier.replace(/_/g, ' ').toLowerCase()}
                          {outcome.character_loss ? ' (character loss)' : ''}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p>The possible outcomes have not been described.</p>
                )}
              </div>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setAuthoredEntry(null)}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={
                  dispatching ||
                  activeCharacterId !== actorId ||
                  chooserIdentity.current !== openingIdentity
                }
                onClick={() => {
                  if (
                    activeCharacterId !== actorId ||
                    chooserIdentity.current !== openingIdentity ||
                    authoredEntry.action === null ||
                    dispatching
                  ) {
                    setAuthoredEntry(null);
                    return;
                  }
                  if (authoredEntry.inputs.some((input) => input.required)) {
                    setAuthoredEntry(null);
                    setInputEntry(authoredEntry);
                    return;
                  }
                  setDispatching(true);
                  void mutateAsync({
                    ref: authoredEntry.action.ref as ActionRef,
                    kwargs: authoredEntry.kwargs,
                  })
                    .then((result) => {
                      if (isDispatchFailure(result))
                        toast.error(
                          result.message ?? `Couldn't ${authoredEntry.label.toLowerCase()}.`
                        );
                      else if (!result.deferred)
                        toast.success(result.message ?? `${authoredEntry.label} complete.`);
                    })
                    .catch(() => toast.error(`Couldn't ${authoredEntry.label.toLowerCase()}.`))
                    .finally(() => {
                      setDispatching(false);
                      setAuthoredEntry(null);
                    });
                }}
              >
                Confirm action
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
      {inputEntry && actorId !== null ? (
        <TargetMenuInputs
          partition={partition}
          actorId={actorId}
          target={target}
          entry={inputEntry}
          open
          submitting={dispatching}
          onOpenChange={(next) => {
            if (!next) setInputEntry(null);
          }}
          onConfirm={(kwargs) => {
            if (
              actorId === null ||
              activeCharacterId !== actorId ||
              chooserIdentity.current !== openingIdentity ||
              dispatching
            ) {
              setInputEntry(null);
              return false;
            }
            setDispatching(true);
            void mutateAsync({
              ref: inputEntry.ref,
              kwargs,
            })
              .then((result) => {
                if (isDispatchFailure(result))
                  toast.error(result.message ?? `Couldn't ${inputEntry.label.toLowerCase()}.`);
                else if (!result.deferred)
                  toast.success(result.message ?? `${inputEntry.label} complete.`);
              })
              .catch(() => toast.error(`Couldn't ${inputEntry.label.toLowerCase()}.`))
              .finally(() => {
                setDispatching(false);
                setInputEntry(null);
              });
            return true;
          }}
        />
      ) : null}
    </>
  );
}
