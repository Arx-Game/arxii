/**
 * PublishBar (#3983 Task 9, plate S-VIII "Publish") — the chapters
 * readiness table plus Publish/Republish/unpublish, computed entirely
 * client-side from the same document `useHouseDocument` already loaded (no
 * extra read). A chapter is "written" when every prose field it owns is
 * non-empty and isn't the literal string `PLACEHOLDER` (Decision 7). Reached
 * by clicking the top bar's `.status` chip (`HouseDocument`) rather than
 * living in the House/Holdings contents rail — the plate's own contents
 * rail never lists a "Publish" entry, and this leaf's `.almanac` drops to
 * two columns (no record rail), matching plate VIII exactly.
 *
 * Realm carries no prose field at all (`RealmLeaf`'s body is entirely
 * backend-derived), so its row is vacuously "written" with a placeholder
 * dash. Estate's placeholder text is the generic "the estate" rather than
 * the plate's example-specific "the seat" wording — nothing in
 * `AlmanachEstateEntry` says whether an estate IS the house's seat.
 */
import type {
  AlmanachDocumentLands,
  AlmanachEstateEntry,
  AlmanachFamily,
  AlmanachHouseDocumentHouse,
} from '../types';

const PLACEHOLDER = 'PLACEHOLDER';

function isWritten(value: string): boolean {
  return value.trim() !== '' && value !== PLACEHOLDER;
}

interface ChapterRow {
  chapter: string;
  written: number;
  total: number;
  placeholder: string;
}

function houseRow(house: AlmanachHouseDocumentHouse): ChapterRow {
  const fields: [string, string][] = [
    ['words', house.words],
    ['colors', house.colors],
    ['sigil', house.sigil_description],
    ['the house', house.description],
  ];
  const missing = fields.filter(([, value]) => !isWritten(value));
  return {
    chapter: 'The House',
    written: fields.length - missing.length,
    total: fields.length,
    placeholder:
      missing.length > 0 ? missing.map(([label]) => label).join(' · ') : 'words · colors · sigil',
  };
}

function familyRow(family: AlmanachFamily): ChapterRow {
  const total = family.nodes.length;
  const missing = family.nodes.filter((node) => !isWritten(node.description));
  return {
    chapter: 'The Family',
    written: total - missing.length,
    total,
    placeholder: missing.length > 0 ? `${missing.length} descriptions` : '—',
  };
}

function landsRow(lands: AlmanachDocumentLands): ChapterRow {
  const total = lands.baronies.length;
  const missing = lands.baronies.filter((barony) => !isWritten(barony.description));
  return {
    chapter: 'Lands',
    written: total - missing.length,
    total,
    placeholder: missing.length > 0 ? missing.map((barony) => barony.name).join(' · ') : '—',
  };
}

function estateRow(estate: AlmanachEstateEntry[]): ChapterRow {
  const first = estate[0];
  const written = first != null && isWritten(first.description) ? 1 : 0;
  return {
    chapter: 'Estate',
    written,
    total: 1,
    placeholder: first == null ? 'not planted yet' : 'the estate',
  };
}

export interface PublishBarProps {
  house: AlmanachHouseDocumentHouse;
  family: AlmanachFamily;
  lands: AlmanachDocumentLands;
  estate: AlmanachEstateEntry[];
  onPublish: (publish: boolean) => void;
}

export function PublishBar({ house, family, lands, estate, onPublish }: PublishBarProps) {
  const rows: ChapterRow[] = [
    houseRow(house),
    familyRow(family),
    { chapter: 'Realm', written: 0, total: 0, placeholder: '—' },
    landsRow(lands),
    estateRow(estate),
  ];
  const published = house.published_at != null;

  return (
    <main className="chapter">
      <h3>House {house.name}</h3>
      <div className="scroll">
        <table className="lad">
          <thead>
            <tr>
              <th scope="col">chapter</th>
              <th scope="col" className="n">
                written
              </th>
              <th scope="col">placeholder</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.chapter}>
                <td>{row.chapter}</td>
                <td className={row.total === 0 || row.written === row.total ? 'n ok' : 'n'}>
                  {row.total === 0 || row.written === row.total
                    ? '✓'
                    : `${row.written} of ${row.total}`}
                </td>
                <td>{row.placeholder}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="savebar">
        <span className="note">
          {published ? `published ${house.published_at?.slice(0, 10)}` : 'draft'}
        </span>
        {published ? (
          <>
            <button type="button" className="btn ghost" onClick={() => onPublish(false)}>
              unpublish
            </button>
            <button type="button" className="btn" onClick={() => onPublish(true)}>
              Republish
            </button>
          </>
        ) : (
          <button type="button" className="btn" onClick={() => onPublish(true)}>
            Publish
          </button>
        )}
      </div>
    </main>
  );
}
