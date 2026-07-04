/**
 * SceneLinesAndVeilsCard — read-only "lines & veils" aggregate for a scene
 * (#1771). Shows the scene participants' SHARED advisory boundaries + shared
 * treasured subjects, from the viewer's own tenure perspective. Never shows
 * an owner or a hard line — the aggregate is anonymized by construction
 * (see world.boundaries.services.scene_lines_and_veils / ADR-0033).
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import MyTenureSelect from '@/components/MyTenureSelect';
import { useSceneLinesAndVeils } from '../queries';

interface Props {
  sceneId: string;
}

export function SceneLinesAndVeilsCard({ sceneId }: Props) {
  const [tenureId, setTenureId] = useState<number | null>(null);
  const { data, isLoading } = useSceneLinesAndVeils(sceneId, tenureId ?? undefined);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Lines &amp; veils</CardTitle>
        <CardDescription>
          Shared content boundaries and treasured subjects for this scene&apos;s cast.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <MyTenureSelect value={tenureId} onChange={setTenureId} label="View as" />

        {tenureId != null && isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-3/4" />
          </div>
        )}

        {tenureId != null && data && (
          <>
            {data.advisories.length === 0 && data.treasured_subjects.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing shared for this scene&apos;s cast yet.
              </p>
            ) : (
              <div className="space-y-3">
                {data.advisories.length > 0 && (
                  <div>
                    <h4 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      Advisories
                    </h4>
                    <ul className="space-y-1">
                      {data.advisories.map((a, idx) => (
                        <li key={`${a.theme_name}-${idx}`} className="text-sm">
                          <span className="font-medium">{a.theme_name}</span>
                          {a.detail && <span className="text-muted-foreground"> — {a.detail}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {data.treasured_subjects.length > 0 && (
                  <div>
                    <h4 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      Treasured subjects
                    </h4>
                    <ul className="space-y-1">
                      {data.treasured_subjects.map((t, idx) => (
                        <li key={`${t.subject_label}-${idx}`} className="text-sm">
                          <span className="font-medium">{t.subject_label}</span>
                          {t.detail && <span className="text-muted-foreground"> — {t.detail}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
