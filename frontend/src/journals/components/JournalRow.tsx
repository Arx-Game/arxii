/**
 * One row of the Reading Room (#3941) — an entry collapsed, and the same entry
 * opened in place.
 *
 * Collapsed it is a band, a writer, a date, a title, who it is about, and the
 * first seven lines. Opened it grows tags, the actions, the responses, the
 * respond form and — last and faint — Mute and Block. Nothing is a mode: the
 * row never navigates away to show more of itself.
 *
 * The list feed carries no body (`JournalEntryListSerializer`), so the text
 * comes from `useJournalEntry(id, open)` and is fetched the moment the reader
 * opens the row. React Query keeps it, so a row that has been opened once
 * shows its clamped first lines when it closes again.
 *
 * Deliberately provider-free: no `useQueryClient`, no `Link`, no router. A
 * stream is twenty of these, and a leaf that needs the whole app's context to
 * render is a leaf that cannot be tested or reused. Where the row does want
 * the query cache (invalidating the feed after a mute), it reads the client
 * out of context and does nothing when there isn't one.
 */
import { useCallback, useContext, useState } from 'react';
import { Link, useInRouterContext } from 'react-router-dom';
import { QueryClientContext } from '@tanstack/react-query';
import { toast } from 'sonner';

import { NominateButton } from '@/components/NominateButton';
import { useCreateBlock, useCreateMute } from '@/social/queries';
import { cn } from '@/lib/utils';

import type { JournalEntrySummary, JournalResponseType, PosthumousOverride } from '../api';
import { formatIcDate, formatPostingDate } from '../dates';
import {
  FIELD_INPUT_CLASS,
  FIELD_LABEL_CLASS,
  PRIMARY_BUTTON_CLASS,
  QUIET_BUTTON_CLASS,
} from '../fieldClasses';
import { PillButton } from './Pill';
import {
  journalsKeys,
  useEditJournalEntry,
  useJournalEntry,
  useRespondToJournal,
} from '../queries';

/** Who is reading. `sheetId` and `personaId` are null for an account with no character docked. */
export interface RowViewer {
  sheetId: number | null;
  personaId: number | null;
  isStaff: boolean;
}

export interface JournalRowProps {
  entry: JournalEntrySummary;
  open: boolean;
  onToggle: () => void;
  viewer: RowViewer;
}

/** The CG Introductions wear their own name in the band; an ordinary entry wears none. */
const KIND_BANDS: Record<string, string> = {
  first_journal: 'First Journal',
  application: 'Application',
  whispers: 'The Whispers',
};

const ACTION_CLASS =
  'jr-sans jr-soft cursor-pointer border-0 bg-transparent p-0 text-[.8125rem] ' +
  'text-muted-foreground hover:text-foreground hover:underline';

const CHIP_CLASS =
  'jr-sans jr-chip rounded-full border px-[.55rem] py-[.05rem] text-[.75rem] text-muted-foreground';

function bandText(entry: JournalEntrySummary): string | null {
  if (entry.revealed_at) return `Post mortem · ${formatPostingDate(entry.revealed_at)}`;
  if (!entry.is_public) return 'Black journal';
  if (entry.kind && entry.kind !== 'entry') return KIND_BANDS[entry.kind] ?? null;
  return null;
}

/**
 * Best-effort feed invalidation. Reads the client straight out of context rather
 * than through `useQueryClient()`, which throws when there is no provider: a row
 * rendered on its own still has to render, and with no cache there is nothing to
 * invalidate anyway.
 */
function useInvalidateFeed() {
  const client = useContext(QueryClientContext);
  return useCallback(() => {
    client?.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
  }, [client]);
}

function stopRowToggle(event: React.MouseEvent) {
  event.stopPropagation();
}

/** The writer's name, linking to their journal — as a router link when there is a router. */
function WriterLink({ to, children }: { to: string; children: React.ReactNode }) {
  const inRouter = useInRouterContext();
  if (!inRouter) {
    return (
      <a href={to} onClick={stopRowToggle} className="no-underline hover:underline">
        {children}
      </a>
    );
  }
  return (
    <Link to={to} onClick={stopRowToggle} className="no-underline hover:underline">
      {children}
    </Link>
  );
}

/**
 * The date, which flips. An entry written in the world shows its IC date; a click
 * shows when it was actually posted, and another click puts it back. With no IC
 * date there is nothing to flip to, so it is plain text.
 */
function DateStamp({ entry }: { entry: JournalEntrySummary }) {
  const [showIc, setShowIc] = useState(true);
  const posted = formatPostingDate(entry.created_at);

  if (!entry.ic_timestamp) {
    return <span>{posted}</span>;
  }

  const ic = formatIcDate(entry.ic_timestamp);
  return (
    <button
      type="button"
      title={showIc ? 'Show posting date' : 'Show IC date'}
      className="cursor-pointer border-0 border-b border-dotted border-transparent bg-transparent p-0 font-[inherit] text-[inherit] text-inherit hover:border-current"
      onClick={(event) => {
        event.stopPropagation();
        setShowIc((previous) => !previous);
      }}
    >
      {showIc ? ic : posted}
    </button>
  );
}

/** After your death, for one black entry. Neither pill is pressed while the entry inherits. */
function AfterDeathPills({ entry }: { entry: JournalEntrySummary }) {
  const editEntry = useEditJournalEntry();

  function choose(override: PosthumousOverride) {
    editEntry.mutate(
      { entryId: entry.id, body: { posthumous_override: override } },
      {
        onError: (err: Error) => toast.error(err.message),
      }
    );
  }

  return (
    <div className="jr-sans flex flex-wrap items-center gap-3 text-[.8125rem]">
      <span className="jr-soft text-muted-foreground">After your death</span>
      <div className="flex flex-wrap gap-2">
        <PillButton
          pressed={entry.posthumous_override === 'reveal'}
          onClick={() => choose('reveal')}
        >
          Reveal
        </PillButton>
        <PillButton pressed={entry.posthumous_override === 'seal'} onClick={() => choose('seal')}>
          Remain sealed
        </PillButton>
      </div>
    </div>
  );
}

/** One response, opened for its text — the feed's response fragment carries only the title. */
function ResponseItem({ response }: { response: JournalEntrySummary }) {
  const [expanded, setExpanded] = useState(false);
  const { data } = useJournalEntry(response.id, expanded);

  return (
    <div className="grid gap-[.15rem]">
      <div className="jr-sans jr-soft flex flex-wrap items-baseline gap-[.6rem] text-[.8125rem] text-muted-foreground">
        {response.response_type ? (
          <span className="rounded-[2px] border px-[.45rem] py-[.05rem] text-[.6875rem] uppercase tracking-[.12em]">
            {response.response_type}
          </span>
        ) : null}
        <span>{response.author_name}</span>
      </div>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={(event) => {
          event.stopPropagation();
          setExpanded((previous) => !previous);
        }}
        className="cursor-pointer border-0 bg-transparent p-0 text-left font-body text-[1.05rem] font-semibold text-inherit hover:underline"
      >
        {response.title}
      </button>
      {expanded && data?.body ? <p className="jr-body m-0">{data.body}</p> : null}
    </div>
  );
}

/** Title and text, for a response the reader is writing. */
function RespondForm({
  entry,
  kind,
  onDone,
}: {
  entry: JournalEntrySummary;
  kind: JournalResponseType;
  onDone: () => void;
}) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const respond = useRespondToJournal();
  const canSubmit = title.trim().length > 0 && body.trim().length > 0 && !respond.isPending;

  function submit() {
    if (!canSubmit) return;
    respond.mutate(
      { entryId: entry.id, body: { title: title.trim(), body, response_type: kind } },
      {
        onSuccess: () => {
          setTitle('');
          setBody('');
          onDone();
        },
        onError: (err: Error) => toast.error(err.message),
      }
    );
  }

  return (
    <div className="grid gap-3" onClick={stopRowToggle} role="presentation">
      <div className="grid gap-[.3rem]">
        <label className={FIELD_LABEL_CLASS} htmlFor={`respond-title-${entry.id}`}>
          Title
        </label>
        <input
          id={`respond-title-${entry.id}`}
          className={FIELD_INPUT_CLASS}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </div>
      <div className="grid gap-[.3rem]">
        <label className={FIELD_LABEL_CLASS} htmlFor={`respond-body-${entry.id}`}>
          Response
        </label>
        <textarea
          id={`respond-body-${entry.id}`}
          className={cn(FIELD_INPUT_CLASS, 'min-h-[5rem] resize-y leading-[1.6]')}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={submit}
          className={PRIMARY_BUTTON_CLASS}
        >
          Post response
        </button>
        <button type="button" onClick={onDone} className={QUIET_BUTTON_CLASS}>
          Cancel
        </button>
      </div>
    </div>
  );
}

/** Title and text, for the writer's own entry. */
function InlineEditor({
  entry,
  initialTitle,
  initialBody,
  onDone,
}: {
  entry: JournalEntrySummary;
  initialTitle: string;
  initialBody: string;
  onDone: () => void;
}) {
  const [title, setTitle] = useState(initialTitle);
  const [body, setBody] = useState(initialBody);
  const editEntry = useEditJournalEntry();
  const canSubmit = title.trim().length > 0 && body.trim().length > 0 && !editEntry.isPending;

  function submit() {
    if (!canSubmit) return;
    editEntry.mutate(
      { entryId: entry.id, body: { title: title.trim(), body } },
      {
        onSuccess: onDone,
        onError: (err: Error) => toast.error(err.message),
      }
    );
  }

  return (
    <div className="grid gap-3" onClick={stopRowToggle} role="presentation">
      <div className="grid gap-[.3rem]">
        <label className={FIELD_LABEL_CLASS} htmlFor={`edit-title-${entry.id}`}>
          Title
        </label>
        <input
          id={`edit-title-${entry.id}`}
          className={FIELD_INPUT_CLASS}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </div>
      <div className="grid gap-[.3rem]">
        <label className={FIELD_LABEL_CLASS} htmlFor={`edit-body-${entry.id}`}>
          Entry
        </label>
        <textarea
          id={`edit-body-${entry.id}`}
          className={cn(FIELD_INPUT_CLASS, 'min-h-[10rem] resize-y leading-[1.6]')}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={submit}
          className={PRIMARY_BUTTON_CLASS}
        >
          Save
        </button>
        <button type="button" onClick={onDone} className={QUIET_BUTTON_CLASS}>
          Cancel
        </button>
      </div>
    </div>
  );
}

/**
 * Mute and Block, last and faint. Mute hides this writer from the reader
 * everywhere IC; Block hides the two of them from each other and wants a reason.
 * Both narrow the feed server-side, so both refresh it.
 */
function Moderation({
  entry,
  viewerPersonaId,
}: {
  entry: JournalEntrySummary;
  viewerPersonaId: number;
}) {
  const [reason, setReason] = useState<string | null>(null);
  const createMute = useCreateMute();
  const createBlock = useCreateBlock();
  const invalidateFeed = useInvalidateFeed();

  function mute() {
    if (entry.author_persona_id === null) return;
    createMute.mutate(
      {
        muted_persona: entry.author_persona_id,
        mute_ic: true,
        mute_ooc: true,
        account_level: true,
      },
      {
        onSuccess: invalidateFeed,
        onError: (err: Error) => toast.error(err.message),
      }
    );
  }

  function block() {
    if (entry.author_persona_id === null || !reason || reason.trim() === '') return;
    createBlock.mutate(
      {
        blocker_persona: viewerPersonaId,
        blocked_persona: entry.author_persona_id,
        reason: reason.trim(),
        account_level: true,
      },
      {
        onSuccess: () => {
          setReason(null);
          invalidateFeed();
        },
        onError: (err: Error) => toast.error(err.message),
      }
    );
  }

  return (
    <div className="grid gap-3 opacity-70">
      <div className="jr-sans flex flex-wrap gap-[1.1rem] text-[.8125rem]">
        <button
          type="button"
          className={ACTION_CLASS}
          onClick={mute}
          disabled={createMute.isPending}
        >
          Mute writer
        </button>
        <button
          type="button"
          className={ACTION_CLASS}
          onClick={(event) => {
            event.stopPropagation();
            setReason('');
          }}
        >
          Block writer
        </button>
      </div>
      {reason !== null ? (
        <div className="grid gap-[.3rem]" onClick={stopRowToggle} role="presentation">
          <label className={FIELD_LABEL_CLASS} htmlFor={`block-reason-${entry.id}`}>
            Reason
          </label>
          <input
            id={`block-reason-${entry.id}`}
            className={FIELD_INPUT_CLASS}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              className={ACTION_CLASS}
              onClick={block}
              disabled={reason.trim() === '' || createBlock.isPending}
            >
              Block
            </button>
            <button type="button" className={ACTION_CLASS} onClick={() => setReason(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function JournalRow({ entry, open, onToggle, viewer }: JournalRowProps) {
  const [editing, setEditing] = useState(false);
  const [respondKind, setRespondKind] = useState<JournalResponseType | null>(null);
  const { data: detail } = useJournalEntry(entry.id, open);

  const isOwn = entry.is_own || (viewer.sheetId !== null && entry.author === viewer.sheetId);
  const isBlack = !entry.is_public && !entry.revealed_at;
  const isRevealed = entry.revealed_at !== null;
  const band = bandText(entry);
  const body = detail?.body ?? '';
  const responses = detail?.responses ?? [];
  const canModerate =
    !isOwn && !isRevealed && entry.author_persona_id !== null && viewer.personaId !== null;

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onToggle();
  }

  function respondWith(kind: JournalResponseType) {
    setRespondKind((previous) => (previous === kind ? null : kind));
  }

  return (
    <article
      className={cn(
        'grid gap-[.35rem] border-t py-[1.1rem] first:border-t-0 first:pt-0',
        isBlack && 'jr-black my-[.35rem] border-t-0 px-5',
        isRevealed && 'border-l-[3px] border-l-primary pl-4'
      )}
      data-entry-id={entry.id}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={onToggle}
        onKeyDown={handleKeyDown}
        className="grid cursor-pointer gap-[.2rem]"
      >
        {band ? (
          <div
            className={cn(
              'jr-sans jr-soft text-[.6875rem] uppercase tracking-[.14em] text-muted-foreground',
              isRevealed && 'text-primary'
            )}
          >
            {band}
          </div>
        ) : null}
        <div className="jr-sans jr-soft flex flex-wrap items-baseline gap-x-[.9rem] gap-y-1 text-[.8125rem] text-muted-foreground">
          <span className="jr-strong font-body text-[1.05rem] font-semibold text-foreground">
            <WriterLink to={`/journals?writer=${entry.author}`}>{entry.author_name}</WriterLink>
          </span>
          <DateStamp entry={entry} />
        </div>
        <h3 className="m-0 font-body text-[1.4rem] font-medium leading-[1.2]">{entry.title}</h3>
        {entry.about_name ? (
          <div className="jr-sans jr-soft text-[.8125rem] text-muted-foreground">
            About <b className="jr-strong font-semibold text-foreground">{entry.about_name}</b>
          </div>
        ) : null}
        {body ? <div className={cn('jr-body font-body', !open && 'jr-clamp')}>{body}</div> : null}
      </div>

      {open ? (
        <div className="grid gap-4 pt-3">
          {entry.tags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {entry.tags.map((tag) => (
                <span key={tag.id} className={CHIP_CLASS}>
                  {tag.name}
                </span>
              ))}
            </div>
          ) : null}

          {editing ? (
            <InlineEditor
              entry={entry}
              initialTitle={detail?.title ?? entry.title}
              initialBody={body}
              onDone={() => setEditing(false)}
            />
          ) : null}

          {!editing && isBlack && isOwn ? (
            <>
              <div className="jr-sans flex flex-wrap gap-[1.1rem] text-[.8125rem]">
                <button type="button" className={ACTION_CLASS} onClick={() => setEditing(true)}>
                  Edit
                </button>
              </div>
              <AfterDeathPills entry={entry} />
            </>
          ) : null}

          {!editing && !isBlack && !isRevealed ? (
            <div className="jr-sans flex flex-wrap items-center gap-[1.1rem] text-[.8125rem]">
              {isOwn ? (
                <button type="button" className={ACTION_CLASS} onClick={() => setEditing(true)}>
                  Edit
                </button>
              ) : null}
              {!isOwn ? (
                <button
                  type="button"
                  className={ACTION_CLASS}
                  aria-pressed={respondKind === 'praise'}
                  onClick={() => respondWith('praise')}
                >
                  Praise
                </button>
              ) : null}
              {!isOwn ? (
                <NominateButton
                  targetType="journal"
                  targetId={entry.id}
                  nomineeName={entry.author_name}
                />
              ) : null}
              {!isOwn && entry.can_retort ? (
                <button
                  type="button"
                  className={ACTION_CLASS}
                  aria-pressed={respondKind === 'retort'}
                  onClick={() => respondWith('retort')}
                >
                  Retort
                </button>
              ) : null}
              {!isOwn && entry.can_retort ? (
                <button
                  type="button"
                  className={ACTION_CLASS}
                  aria-pressed={respondKind === 'condemn'}
                  onClick={() => respondWith('condemn')}
                >
                  Condemn
                </button>
              ) : null}
              {entry.response_count > 0 ? (
                <span className="jr-soft text-muted-foreground">
                  {entry.response_count} response{entry.response_count === 1 ? '' : 's'}
                </span>
              ) : null}
            </div>
          ) : null}

          {!editing && responses.length > 0 ? (
            <div className="grid gap-3 border-l-2 pl-4">
              {responses.map((response) => (
                <ResponseItem key={response.id} response={response} />
              ))}
            </div>
          ) : null}

          {!editing && respondKind !== null ? (
            <RespondForm entry={entry} kind={respondKind} onDone={() => setRespondKind(null)} />
          ) : null}

          {!editing && canModerate && viewer.personaId !== null ? (
            <Moderation entry={entry} viewerPersonaId={viewer.personaId} />
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
