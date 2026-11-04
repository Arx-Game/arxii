import type { LadderRow } from '@/almanach/types';

interface SelectPickersProps {
  realms: { id: number; name: string }[];
  realmId: number | null;
  onRealm: (id: number | null) => void;
  ladderRows: LadderRow[];
  focusTitleId: number | null;
  onTitle: (id: number | null) => void;
}

/** A state word on a picker row: only Titular and Potential say anything (#4983). */
function rowStateSuffix(row: LadderRow): string {
  return row.state === 'Titular' || row.state === 'Potential' ? ` · ${row.state}` : '';
}

/**
 * Select mode's realm and domain pickers (#4983): the way a title with no land, a
 * titular or potential crown, is selected on the map.
 */
export function SelectPickers({
  realms,
  realmId,
  onRealm,
  ladderRows,
  focusTitleId,
  onTitle,
}: SelectPickersProps) {
  return (
    <>
      <select
        className="h-8 rounded-md border bg-background px-2 text-sm"
        value={realmId ?? ''}
        onChange={(event) => onRealm(event.target.value ? Number(event.target.value) : null)}
        aria-label="realm"
        data-testid="select-realm"
      >
        <option value="">Realm…</option>
        {realms.map((realm) => (
          <option key={realm.id} value={realm.id}>
            {realm.name}
          </option>
        ))}
      </select>
      <select
        className="h-8 max-w-xs rounded-md border bg-background px-2 text-sm"
        value={focusTitleId ?? ''}
        onChange={(event) => onTitle(event.target.value ? Number(event.target.value) : null)}
        aria-label="domain"
        data-testid="select-domain"
        disabled={realmId == null}
      >
        <option value="">Domain…</option>
        {ladderRows.map((row) => (
          <option key={row.title_id} value={row.title_id}>
            {row.name || `unnamed ${row.tier}`} · {row.tier}
            {rowStateSuffix(row)}
          </option>
        ))}
      </select>
    </>
  );
}
