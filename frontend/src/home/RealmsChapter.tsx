/**
 * RealmsChapter — "Chapter the First: Of Those Who Wake" (#3305).
 *
 * Replaces the reference mockup's five static Beginnings with live
 * StartingArea rows (one per realm), accented in that realm's own palette
 * via a nested `data-realm` wrapper. Rows expand in place (accordion, one
 * open at a time) to that realm's Beginnings list.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Skeleton } from '@/components/ui/skeleton';
import { usePublicBeginnings, usePublicStartingAreas } from './queries';

function BeginningsList({ startingAreaId }: { startingAreaId: number }) {
  const { data: beginnings, isLoading } = usePublicBeginnings(startingAreaId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  if (!beginnings || beginnings.length === 0) {
    return null;
  }

  return (
    <div>
      {beginnings.map((beginning) => (
        <article key={beginning.id} className="gatefold-begin-item">
          <h4>{beginning.name}</h4>
          <p>{beginning.description}</p>
        </article>
      ))}
    </div>
  );
}

export function RealmsChapter() {
  const { data: startingAreas, isLoading } = usePublicStartingAreas();
  const [openAreaId, setOpenAreaId] = useState<string | undefined>(undefined);

  return (
    <div className="gatefold-leaf" id="beginnings">
      <div className="gatefold-leaf-main">
        <span className="gatefold-chapter-no">Chapter the First</span>
        <h2>Of Those Who Wake</h2>
        <div className="gatefold-leaf-body">
          {/* PLACEHOLDER: Apostate rewrite */}
          <p>
            Every character begins somewhere the world has already noticed. These are Beginnings:
            written doors into the story, each with its questions left open for you to answer.
          </p>
        </div>
        {isLoading ? (
          <div className="mt-8 space-y-4">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-6 w-2/5" />
          </div>
        ) : startingAreas && startingAreas.length > 0 ? (
          <Accordion
            type="single"
            collapsible
            className="mt-8"
            value={openAreaId}
            onValueChange={setOpenAreaId}
          >
            {startingAreas.map((area) => (
              <AccordionItem
                key={area.id}
                value={String(area.id)}
                data-realm={area.realm_theme}
                className="gatefold-realm-item"
              >
                <AccordionTrigger className="gatefold-realm-trigger">
                  <span className="gatefold-realm-name" style={{ color: 'hsl(var(--primary))' }}>
                    {area.name}
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <p className="gatefold-realm-desc">{area.description}</p>
                  <BeginningsList startingAreaId={area.id} />
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        ) : null}
        <p className="gatefold-more-line">
          <Link to="/roster">
            Browse every Beginning and the character roster <span aria-hidden="true">→</span>
          </Link>
        </p>
      </div>
      <aside>
        <span className="gatefold-note">
          <b>The Roster</b> keeps established characters as well: lives the world already knows,
          with kin, debts, and rivals in place. <Link to="/roster">See who waits.</Link>
        </span>
        <span className="gatefold-note">
          <b>Two ways in.</b> Begin a life of your own, or take up one the world already knows.
        </span>
      </aside>
    </div>
  );
}
