/**
 * The Realms hub at /realms (#3725): six cards, each in its realm's palette, each
 * carrying only the name, the formal name and the first motto, each a link to the
 * realm's page. Nothing else on it (reviewer, 2026-09-08). The visitor's own theme
 * stays; each card wraps itself in `data-realm` the way the landing page's realm
 * rows do, so six palettes sit on one page.
 */

import { Link } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { useRealms } from '../queries';
import '../realm.css';

export function RealmsHubPage() {
  const { data: realms, isLoading } = useRealms();

  return (
    <main className="realms-hub">
      <span className="realm-eyebrow">World</span>
      <h1>Realms</h1>
      {isLoading && (
        <div className="realms-hub-grid" aria-busy="true">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      )}
      {realms && realms.length > 0 && (
        <div className="realms-hub-grid">
          {realms.map((realm) => (
            <Link
              key={realm.id}
              to={`/realms/${realm.slug}`}
              className="realms-hub-card"
              data-realm={realm.theme}
            >
              <h2>{realm.name}</h2>
              {realm.formal_name && <p className="realm-formal">{realm.formal_name}</p>}
              {realm.first_motto && <p className="realm-motto">{realm.first_motto}</p>}
            </Link>
          ))}
        </div>
      )}
      {realms && realms.length === 0 && <p className="realm-empty">No realms are recorded yet.</p>}
    </main>
  );
}
