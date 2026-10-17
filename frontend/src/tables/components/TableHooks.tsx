/**
 * TableHooks (#4397): the Hooks tab of a GM table, for the GM and staff only.
 *
 * One block per active member: every hook the character carries (a creation
 * pick's secret, a staff-written one, a line the player left) with the truths
 * the GM wrote under it. The GM adds a hook, or a truth under one; a truth is
 * unknown to the player until it is revealed, so this surface shows what the
 * player cannot see and never renders for a member or a guest.
 */

import { useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { useAddPlayerHook, usePlayerHooks, useTableMembers } from '../queries';
import type { GMTable, GMTableMembership, TableHook } from '../types';

interface TableHooksProps {
  table: GMTable;
}

export function TableHooks({ table }: TableHooksProps) {
  const { data, isLoading } = useTableMembers(table.id, { active: true });
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }
  const members = data?.results ?? [];
  if (members.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">No active members at this table.</p>
    );
  }
  return (
    <div className="space-y-6">
      {members.map((membership) => (
        <MemberHooks key={membership.id} tableId={table.id} membership={membership} />
      ))}
    </div>
  );
}

function MemberHooks({ tableId, membership }: { tableId: number; membership: GMTableMembership }) {
  const sheetId = membership.character_sheet;
  const { data: hooks, isLoading } = usePlayerHooks(tableId, sheetId);
  const add = useAddPlayerHook(tableId, sheetId);
  const [newHook, setNewHook] = useState('');

  return (
    <section aria-labelledby={`hooks-${membership.id}`} className="rounded border p-3">
      <h3 id={`hooks-${membership.id}`} className="font-medium">
        {membership.persona_name}
      </h3>
      {isLoading && <Skeleton className="mt-2 h-12 w-full" />}
      {!isLoading && (hooks ?? []).length === 0 && (
        <p className="mt-2 text-sm text-muted-foreground">No hooks yet.</p>
      )}
      {!isLoading && (hooks ?? []).length > 0 && (
        <ul className="mt-2 space-y-3">
          {(hooks ?? []).map((hook) => (
            <HookRow
              key={hook.id}
              hook={hook}
              onAddTruth={(content) => add.mutate({ hook: hook.id, content })}
            />
          ))}
        </ul>
      )}
      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const content = newHook.trim();
          if (!content) return;
          add.mutate({ content }, { onSuccess: () => setNewHook('') });
        }}
      >
        <label htmlFor={`new-hook-${membership.id}`} className="text-sm">
          Add a hook
        </label>
        <textarea
          id={`new-hook-${membership.id}`}
          rows={2}
          className="rounded border bg-background p-2 text-sm"
          value={newHook}
          onChange={(e) => setNewHook(e.target.value)}
        />
        <div>
          <button
            type="submit"
            className="rounded border px-2 py-1 text-xs hover:bg-accent"
            disabled={add.isPending || !newHook.trim()}
          >
            Add hook
          </button>
        </div>
      </form>
    </section>
  );
}

function HookRow({ hook, onAddTruth }: { hook: TableHook; onAddTruth: (content: string) => void }) {
  const [open, setOpen] = useState(false);
  const [truth, setTruth] = useState('');
  return (
    <li className="rounded bg-muted/40 p-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm">{hook.content}</p>
          <p className="text-xs text-muted-foreground">
            {hook.kind}
            {!hook.aware && ' · the player does not know this'}
          </p>
          {hook.consequences && (
            <p className="text-xs text-muted-foreground">If it surfaces: {hook.consequences}</p>
          )}
        </div>
        <button
          type="button"
          className="rounded border px-2 py-1 text-xs hover:bg-accent"
          aria-expanded={open}
          onClick={() => setOpen((prev) => !prev)}
        >
          {open ? 'Cancel' : 'Add a truth'}
        </button>
      </div>
      {hook.truths.length > 0 && (
        <ul className="mt-2 space-y-1 border-l pl-3">
          {hook.truths.map((t) => (
            <li key={t.id} className="text-sm">
              {t.content}
              <span className="ml-1 text-xs text-muted-foreground">
                {t.subject_aware ? '(revealed)' : '(the player does not know this)'}
              </span>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const content = truth.trim();
            if (!content) return;
            onAddTruth(content);
            setTruth('');
            setOpen(false);
          }}
        >
          <label htmlFor={`truth-${hook.id}`} className="text-sm">
            The truth under it
          </label>
          <textarea
            id={`truth-${hook.id}`}
            rows={2}
            className="rounded border bg-background p-2 text-sm"
            value={truth}
            onChange={(e) => setTruth(e.target.value)}
          />
          <div>
            <button
              type="submit"
              className="rounded border px-2 py-1 text-xs hover:bg-accent"
              disabled={!truth.trim()}
            >
              Write it
            </button>
          </div>
        </form>
      )}
    </li>
  );
}
