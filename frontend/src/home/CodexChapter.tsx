/**
 * CodexChapter — "Chapter the Second: Of the Empty City" (#3305).
 *
 * Body prose is verbatim Apostate copy (arx-the-empty-city.md) — not
 * agent-drafted, so it carries no PLACEHOLDER marker. The index list below it
 * is live: `useFeaturedLore()` (home-scoped — no `throwOnError`, unlike the
 * Codex page's own `useFeaturedCodexEntries`; a codex API failure must hide
 * the index list, never blank the whole landing page).
 */

import { Link } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { useFeaturedLore } from './queries';

export function CodexChapter() {
  const { data: entries, isLoading } = useFeaturedLore();

  return (
    <div className="gatefold-leaf" id="codex">
      <div className="gatefold-leaf-main">
        <span className="gatefold-chapter-no">Chapter the Second</span>
        <h2>Of the Empty City</h2>
        <div className="gatefold-leaf-body">
          {/* Verbatim Apostate prose, arx-the-empty-city.md */}
          <p className="gatefold-dropcap">
            The songs outside call it the City of Heroes. The people who live in it call it home,
            and home is a city built for three million that holds perhaps fifty thousand, the living
            gathered in the Ward of the Compact while eight dark wards stand empty around them,
            swept and lamplit all the same. Arx is, at its heart, a necropolis: a city of graves and
            memorials, built to hold the dead and to keep their testaments. Its motto is learned by
            every Caretaker child:{' '}
            <span className="gatefold-caps">“As Arx endures, we remember.”</span>
          </p>
          <p>
            For ages, the most precious relics and secrets in the world were entrusted to Arx for
            their safety, because nothing could touch them behind the Shroud. And now the Shroud has
            fallen.
          </p>
        </div>
        {isLoading ? (
          <div className="mt-8 space-y-4">
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        ) : entries && entries.length > 0 ? (
          <ul className="gatefold-index-list">
            {entries.map((entry) => (
              <li key={entry.id}>
                <span className="gatefold-entry-name">
                  <Link to={`/codex?entry=${entry.id}`}>{entry.name}</Link>
                </span>
                <p>{entry.summary}</p>
              </li>
            ))}
          </ul>
        ) : null}
        <p className="gatefold-more-line">
          <Link to="/codex">
            Open the Codex <span aria-hidden="true">→</span>
          </Link>
        </p>
      </div>
      <aside>
        <span className="gatefold-note">
          <b>The Codex</b> holds the world’s public record: realms, peoples, laws, and faiths,
          written to be read before you ever make a character.
        </span>
        <span className="gatefold-note">
          <b>No downloads.</b> The whole world runs in your browser, and it keeps its ledger between
          scenes.
        </span>
      </aside>
    </div>
  );
}
