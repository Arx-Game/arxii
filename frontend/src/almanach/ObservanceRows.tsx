/**
 * ObservanceRows (#4206) — the editor for a house's days of remembrance, one
 * row per day: its name, the IC month and day, and the house's prose for it.
 * Shared by the founder's House chapter (bound to the browser draft) and the
 * Almanach document's House chapter (staged beside the other stylings and
 * saved with them). Month and day are plain number inputs, the same shape the
 * deity editor gives a feast day; the spelled date ("Masquing 18 (10/18)")
 * comes back from the server on the read payload, never computed here.
 */

export interface ObservanceRow {
  ic_month: number;
  ic_day: number;
  name: string;
  lore: string;
}

export interface ObservanceRowsProps {
  /** Prefix for the row controls' ids, so two chapters on one page never collide. */
  idPrefix: string;
  rows: ObservanceRow[];
  onChange: (rows: ObservanceRow[]) => void;
}

function newObservanceRow(): ObservanceRow {
  return { ic_month: 1, ic_day: 1, name: '', lore: '' };
}

export function ObservanceRows({ idPrefix, rows, onChange }: ObservanceRowsProps) {
  const patch = (index: number, change: Partial<ObservanceRow>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  const remove = (index: number) => onChange(rows.filter((_, i) => i !== index));

  return (
    <div className="field">
      <span className="label">days of remembrance</span>
      <ul className="entries observances">
        {rows.map((row, index) => (
          <li key={index}>
            <span className="mark">◆</span>
            <span className="observance">
              <div className="row3">
                <div className="field">
                  <label htmlFor={`${idPrefix}-observance-${index}-name`}>name</label>
                  <input
                    id={`${idPrefix}-observance-${index}-name`}
                    type="text"
                    value={row.name}
                    onChange={(event) => patch(index, { name: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor={`${idPrefix}-observance-${index}-month`}>month</label>
                  <input
                    id={`${idPrefix}-observance-${index}-month`}
                    type="number"
                    min={1}
                    max={12}
                    value={row.ic_month}
                    onChange={(event) => patch(index, { ic_month: Number(event.target.value) })}
                  />
                </div>
                <div className="field">
                  <label htmlFor={`${idPrefix}-observance-${index}-day`}>day</label>
                  <input
                    id={`${idPrefix}-observance-${index}-day`}
                    type="number"
                    min={1}
                    max={31}
                    value={row.ic_day}
                    onChange={(event) => patch(index, { ic_day: Number(event.target.value) })}
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor={`${idPrefix}-observance-${index}-lore`}>the day</label>
                <textarea
                  id={`${idPrefix}-observance-${index}-lore`}
                  className="prose"
                  value={row.lore}
                  onChange={(event) => patch(index, { lore: event.target.value })}
                />
              </div>
            </span>
            <span className="rt">
              <button
                type="button"
                aria-label={`Remove day of remembrance ${index + 1}`}
                onClick={() => remove(index)}
              >
                remove
              </button>
            </span>
          </li>
        ))}
      </ul>
      <div className="chips">
        <button
          type="button"
          className="chip acc"
          aria-label="Add a day of remembrance"
          onClick={() => onChange([...rows, newObservanceRow()])}
        >
          ⊕ a day
        </button>
      </div>
    </div>
  );
}
