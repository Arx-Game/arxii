/**
 * DeedPage (#3466 Task 10) — the app's first deed view: a legendary deed, the honors
 * it has received, and the form to write one more.
 *
 * Route: /deeds/:id. Reached from a character sheet's Reputation tab, "Recent Deeds"
 * card (`renown/components/DeedsLogCard.tsx`), which links each deed's title through
 * to this page.
 *
 * Scope is deliberately narrow (per the task brief): the deed, its honors, and the
 * honor form. No deed browsing/search, no spreading UI — those stay on the roadmap.
 */
import { useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import { HonorForm } from './HonorForm';
import { HonorList } from './HonorList';
import { useDeed } from '../queries';

function DeedPageSkeleton() {
  return (
    <div className="animate-pulse space-y-6" data-testid="deed-page-loading">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-40" />
      </div>
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

/**
 * Renders when `can_honor.allowed` is false. Per the API contract, `reason` is ALWAYS
 * populated in this case — displaying it is the whole point (a greyed-out control with
 * no explanation is exactly the failure mode this is here to avoid). `hares_required`/
 * `value_added` are null here (either the viewer is ineligible, or the rite has no price
 * configured for their level yet) — there is nothing to preview, so no cost is shown.
 */
function CanHonorRefusal({ reason }: { reason: string | null }) {
  return (
    <p
      className="rounded-md bg-muted px-4 py-3 text-sm text-muted-foreground"
      data-testid="can-honor-reason"
    >
      {reason ?? 'You cannot honor this deed right now.'}
    </p>
  );
}

export function DeedPageContent({ deedId }: { deedId: number }) {
  const { data: deed, isLoading } = useDeed(deedId);

  if (isLoading) {
    return <DeedPageSkeleton />;
  }

  if (!deed) {
    return <p className="py-8 text-center text-muted-foreground">Deed not found.</p>;
  }

  const { can_honor } = deed;
  // Only render the form when the viewer is allowed AND a price was actually computed —
  // `allowed: true` always carries non-null cost fields per the backend contract, but the
  // null check keeps this from crashing (rather than showing a bogus "null Hares" cost) if
  // that contract is ever violated.
  const showHonorForm =
    can_honor.allowed && can_honor.hares_required != null && can_honor.value_added != null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-xl">{deed.title}</CardTitle>
            <Badge variant="outline">{deed.persona.name}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm">{deed.description}</p>
          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
            <span>
              Base legend: <span data-testid="deed-base-value">{deed.base_value}</span>
            </span>
            {deed.event && (
              <span>
                Event: {deed.event.title} (ceiling {deed.ceiling})
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Honors</h2>
        <HonorList honors={deed.honors} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Honor This Deed</h2>
        {showHonorForm ? (
          <HonorForm
            deedId={deed.id}
            hareCost={can_honor.hares_required as number}
            valueAdded={can_honor.value_added as number}
          />
        ) : (
          <CanHonorRefusal reason={can_honor.reason} />
        )}
      </section>
    </div>
  );
}

export function DeedPage() {
  const { id = '' } = useParams<{ id: string }>();
  const deedId = parseInt(id, 10);

  if (isNaN(deedId) || deedId <= 0) {
    return (
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <p className="text-muted-foreground">Invalid deed ID.</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <DeedPageContent deedId={deedId} />
    </div>
  );
}
