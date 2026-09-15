/**
 * CodexChapter — "Chapter the First: Of the Empty City" (#3305; first since #3723: what
 * kind of game this is, for a visitor who has never seen a MU, before who they may wake as).
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

  const renderEntries = () => {
    if (isLoading) {
      return (
        <div className="mt-8 space-y-4">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-5 w-2/3" />
        </div>
      );
    }
    if (entries && entries.length > 0) {
      return (
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
      );
    }
    return null;
  };

  return (
    <div className="gatefold-leaf" id="codex">
      <div className="gatefold-leaf-main">
        <span className="gatefold-chapter-no">Chapter the First</span>
        <h2>Of the Empty City</h2>
        <div className="gatefold-leaf-body">
          {/* Apostate's prose, verbatim (#3723). */}
          <p className="gatefold-dropcap">
            Arx is a collaborative text-based storytelling game set in a shared world whose story
            can be influenced and changed by all the players. Much an MMO writ small or many
            simultaneous roleplaying game tabletops in a shared environment, the players' stories
            and roleplay shape the world and determine its outcome.
          </p>
        </div>
        {renderEntries()}
        <p className="gatefold-more-line">
          <Link to="/codex">
            Open the Codex <span aria-hidden="true">→</span>
          </Link>
        </p>
      </div>
      <aside>
        {/* Apostate's prose, verbatim (#3723). */}
        <span className="gatefold-note">
          <b>The Codex</b> holds the world's public knowledge, and when you are logged onto a
          character, everything known by the character as well.
        </span>
        <span className="gatefold-note">
          <b>No downloads.</b> The game can be played entirely in your browser.
        </span>
      </aside>
    </div>
  );
}
