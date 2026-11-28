/**
 * The desk (#3941) — Write folds it open at the top of the stream rather than
 * taking the reader to a page of its own, so what you are writing sits above
 * what you have been reading.
 *
 * It owns the posting: the fields, the week's remaining rewarded entries, and
 * Discard/Post entry. A refusal from the gate (`{detail}` from the backend,
 * parsed into the error's message) is shown where the writer is looking, not
 * only in a toast that fades.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import { useActiveCharacterId } from '@/gm-adjudication/useActiveCharacterId';
import { useRefreshRecordedActs } from '@/magic/queries';
import { reachFields } from '@/magic/reach';
import { reflectionFields } from '@/magic/reflection';

import type { CreateJournalEntryRequest } from '../api';
import { PRIMARY_BUTTON_CLASS, QUIET_BUTTON_CLASS } from '../fieldClasses';
import { useCreateJournalEntry, useJournalSettings } from '../queries';
import {
  EMPTY_ENTRY_FIELDS,
  isAboutUnresolved,
  isReachUnfinished,
  isReflectionUnfinished,
  type JournalEntryFieldsValue,
} from '../entryFields';
import { JournalEntryFields } from './JournalEntryFields';

export interface JournalDeskProps {
  onPosted: () => void;
  onDiscard: () => void;
}

export function JournalDesk({ onPosted, onDiscard }: JournalDeskProps) {
  const [value, setValue] = useState<JournalEntryFieldsValue>(EMPTY_ENTRY_FIELDS);
  const createEntry = useCreateJournalEntry();
  const refreshRecordedActs = useRefreshRecordedActs(useActiveCharacterId());
  const { data: settings } = useJournalSettings();

  // A name typed into About that has not resolved to anybody holds the button:
  // posting now would silently drop the subject the writer asked for.
  const canSubmit =
    value.title.trim().length > 0 &&
    value.body.trim().length > 0 &&
    !isAboutUnresolved(value) &&
    !isReflectionUnfinished(value) &&
    !isReachUnfinished(value) &&
    !createEntry.isPending;
  const errorMessage =
    createEntry.isError && createEntry.error instanceof Error ? createEntry.error.message : null;
  const rewardedLeft = settings
    ? Math.max(0, settings.rewarded_posts_per_week - settings.posts_this_week)
    : null;

  function post() {
    if (!canSubmit) return;
    const payload: CreateJournalEntryRequest = {
      title: value.title.trim(),
      body: value.body,
      is_public: value.isPublic,
      tags: value.tags,
      about: value.about?.id ?? null,
      ...reflectionFields(value.reflection),
      ...reachFields(value.reach),
    };
    // Never send a no-op override: INHERIT is what the backend already does.
    if (value.posthumousOverride !== 'inherit') {
      payload.posthumous_override = value.posthumousOverride;
    }
    createEntry.mutate(payload, {
      onSuccess: (entry) => {
        toast.success('Journal entry recorded.');
        if (entry.reflection_line) toast.success(entry.reflection_line);
        // A refused mark leaves the entry posted; its line says why and is shown as the error it is.
        if (entry.mark_line) {
          if (entry.mark_recorded === false) toast.error(entry.mark_line);
          else toast.success(entry.mark_line);
        }
        refreshRecordedActs();
        setValue(EMPTY_ENTRY_FIELDS);
        onPosted();
      },
      onError: (err: Error) => toast.error(err.message),
    });
  }

  return (
    <section className="mb-6 grid gap-5 border-b pb-6" aria-label="Write in your journal">
      <div className="jr-sans text-[.6875rem] uppercase tracking-[.14em] text-muted-foreground">
        Write in your journal
      </div>

      <JournalEntryFields value={value} onChange={setValue} showAfterDeath />

      {errorMessage ? (
        <p className="jr-sans m-0 text-[.875rem] text-destructive" data-testid="journal-desk-error">
          {errorMessage}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-4">
        {rewardedLeft !== null && settings ? (
          <span className="jr-sans text-[.8125rem] text-muted-foreground">
            <b className="font-semibold text-foreground">{rewardedLeft}</b> of{' '}
            {settings.rewarded_posts_per_week} rewarded entries left this week
          </span>
        ) : null}
        <span className="ml-auto flex flex-wrap gap-2">
          <button type="button" className={QUIET_BUTTON_CLASS} onClick={onDiscard}>
            Discard
          </button>
          <button
            type="button"
            className={PRIMARY_BUTTON_CLASS}
            disabled={!canSubmit}
            onClick={post}
          >
            Post entry
          </button>
        </span>
      </div>
    </section>
  );
}
