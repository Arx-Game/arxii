/**
 * The tracking dashboard (#3780): derived, aggregate, paginated data on its own page, not
 * folded into the edit form. The pool sits in the header beside "Send Vision…", since
 * spending the pool and seeing how much it has are one GM moment. Tabs: Overview, Worship
 * (contributors, offerings and most devoted on one page), Temples & Shrines, Prayers,
 * Visions, Relics, Codex Entries.
 */

import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';
import { VISION_FRAME_CLASS, VISION_GLYPH, VISION_TEXT_CLASS } from '@/worship/visionStyle';
import { SendVisionFromBeingDialog } from '../components/SendVisionFromBeingDialog';
import { VisibilityBadge } from '../components/VisibilityBadge';
import { tierOf } from '../visibility';
import {
  useBeingPage,
  useBeingPrayers,
  useBeingVisions,
  useCodexRows,
  useOverview,
  useRelics,
  useSites,
  useWorshipTab,
} from '../queries';
import type { StaffPrayer, Visibility } from '../types';

type Tab = 'overview' | 'worship' | 'sites' | 'prayers' | 'visions' | 'relics' | 'codex';

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}

function PrayerBadge({ prayer }: { prayer: StaffPrayer }) {
  if (prayer.dire_straits) {
    return (
      <Badge variant="destructive" data-testid="prayer-dire">
        Dire · {prayer.dire_straits.replace('_', ' ')}
        {prayer.answered ? ' · answered' : ' · intervention rolled'}
      </Badge>
    );
  }
  if (prayer.devotion_granted) {
    return (
      <Badge variant="secondary" data-testid="prayer-devotion">
        Act of devotion
      </Badge>
    );
  }
  if (prayer.answered) {
    return (
      <Badge variant="outline" data-testid="prayer-answered">
        Vision sent
      </Badge>
    );
  }
  return null;
}

export function BeingDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const beingId = Number(id);
  const [tab, setTab] = useState<Tab>('overview');
  const { data: page } = useBeingPage(beingId);
  const { data: overview } = useOverview(beingId);
  const { data: worship } = useWorshipTab(beingId, tab === 'worship');
  const { data: sites } = useSites(beingId, tab === 'sites');
  const { data: prayers } = useBeingPrayers(beingId, tab === 'prayers');
  const { data: visions } = useBeingVisions(beingId, tab === 'visions');
  const { data: relics } = useRelics(beingId, tab === 'relics');
  const { data: codex } = useCodexRows(beingId, tab === 'codex');

  if (!page) {
    return <p className="container mx-auto max-w-6xl px-4 py-8 text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <Link to="/staff/pantheon" className="text-xs text-muted-foreground hover:underline">
        ← Deity Editor
      </Link>
      <div className="mb-6 mt-1 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{page.name}</h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <span>{page.domains || 'No domains yet'}</span>
            <VisibilityBadge visibility={page.visibility as Visibility} />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums" data-testid="header-pool">
              {page.resonance_pool.toLocaleString()}
            </div>
            <div className="text-xs text-muted-foreground">resonance pool</div>
          </div>
          <SendVisionFromBeingDialog beingId={beingId} beingName={page.name} />
          <Button asChild variant="outline">
            <Link to={`/staff/pantheon/${beingId}/edit`}>Edit</Link>
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
        <TabsList className="flex flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="worship">Worship</TabsTrigger>
          <TabsTrigger value="sites">Temples &amp; Shrines</TabsTrigger>
          <TabsTrigger value="prayers">Prayers</TabsTrigger>
          <TabsTrigger value="visions">Visions</TabsTrigger>
          <TabsTrigger value="relics">Relics</TabsTrigger>
          <TabsTrigger value="codex">Codex Entries</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              value={(overview?.resonance_pool ?? page.resonance_pool).toLocaleString()}
              label="resonance pool"
            />
            <Stat
              value={(overview?.lifetime_worship ?? 0).toLocaleString()}
              label="lifetime worship"
            />
            <Stat
              value={overview?.most_devoted_name ?? '—'}
              label={
                overview?.most_devoted_favor != null
                  ? `most devoted · ${overview.most_devoted_favor} favor`
                  : 'most devoted'
              }
            />
            <Stat value={String(overview?.site_count ?? 0)} label="shrines & temples" />
          </div>
          <Card>
            <CardContent className="py-4">
              <p className="mb-3 text-sm font-semibold">Recent activity</p>
              {(overview?.recent_activity ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing yet.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {overview?.recent_activity.map((row, index) => (
                    <li
                      key={index}
                      className="flex justify-between gap-4"
                      data-testid="activity-row"
                    >
                      <span>{row.text}</span>
                      <span className="text-muted-foreground">
                        {row.note} · {formatRelativeTime(row.when)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="worship" className="space-y-4">
          <Card>
            <CardContent className="py-4">
              <p className="mb-2 text-sm font-semibold">Most devoted</p>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th>Rank</th>
                    <th>Character</th>
                    <th>Favor</th>
                    <th>Lifetime</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(worship?.most_devoted ?? []).map((row) => (
                    <tr key={row.rank} data-testid="devotee-row">
                      <td>{row.rank}</td>
                      <td>{row.character_name}</td>
                      <td className="tabular-nums">{row.favor}</td>
                      <td className="tabular-nums">{row.lifetime_favor}</td>
                      <td>{row.valence && <Badge variant="outline">{row.valence}</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <p className="mb-2 text-sm font-semibold">Contributors</p>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th>Character</th>
                    <th>Amount</th>
                    <th>Reason</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {(worship?.contributors ?? []).map((row, index) => (
                    <tr key={index}>
                      <td>{row.character_name || 'Someone'}</td>
                      <td className="tabular-nums">{row.amount}</td>
                      <td>{row.reason}</td>
                      <td className="text-muted-foreground">{formatRelativeTime(row.when)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <p className="mb-2 text-sm font-semibold">Offerings</p>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th>Item</th>
                    <th>Offered by</th>
                    <th>Value</th>
                    <th>Credited</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {(worship?.offerings ?? []).map((row, index) => (
                    <tr key={index}>
                      <td>{row.item_name}</td>
                      <td>{row.offered_by}</td>
                      <td className="tabular-nums">{row.item_value}</td>
                      <td className="tabular-nums">
                        {row.amount != null && row.amount > row.item_value ? (
                          <Badge variant="secondary">{row.amount} · favored</Badge>
                        ) : (
                          (row.amount ?? '—')
                        )}
                      </td>
                      <td className="text-muted-foreground">
                        {row.when ? formatRelativeTime(row.when) : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sites" className="space-y-3">
          {(sites ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground">No shrine or temple yet.</p>
          )}
          {(sites ?? []).map((site, index) => (
            <Card key={index}>
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <div>
                  <div className="font-semibold">
                    {site.name}{' '}
                    <span className="font-normal text-muted-foreground">
                      · {site.kind === 'temple' ? 'Temple' : 'Shrine'}
                      {site.place ? ` · ${site.place}` : ''}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {site.kind === 'temple'
                      ? 'Every room in the building is sanctified.'
                      : 'One dedicated room.'}
                    {site.founder_name ? ` Founded by ${site.founder_name}.` : ''}
                  </div>
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  <div>
                    {site.tier_name || 'Unranked'} · +{site.bonus_percent}%
                  </div>
                  <div className="tabular-nums">{site.consecration_points} points</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="prayers" className="space-y-3">
          {(prayers?.results ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground">No prayers yet.</p>
          )}
          {(prayers?.results ?? []).map((prayer) => (
            <Card key={prayer.id}>
              <CardContent className="py-4" data-testid="prayer-card">
                <div className="mb-1 flex items-center justify-between gap-3">
                  <span className="font-semibold">{prayer.character_name}</span>
                  <PrayerBadge prayer={prayer} />
                </div>
                <p className="text-sm italic">“{prayer.text}”</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {formatRelativeTime(prayer.prayed_at)}
                  {prayer.place ? ` · at ${prayer.place}` : ''}
                </p>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="visions" className="space-y-3">
          {(visions?.results ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground">No vision sent yet.</p>
          )}
          {(visions?.results ?? []).map((vision) => (
            <article
              key={vision.id}
              className={cn(VISION_FRAME_CLASS, 'px-3 py-2')}
              data-testid="vision-row"
            >
              <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span aria-hidden="true" className="text-emerald-600 dark:text-emerald-400">
                  {VISION_GLYPH}
                </span>
                <span>To {vision.recipient_name}</span>
                <span>· {vision.reveal_source ? 'source revealed' : 'source concealed'}</span>
                {vision.sent_by_name && <span>· by {vision.sent_by_name}</span>}
                <span className="ml-auto">
                  −{vision.resonance_spent} pool · {formatRelativeTime(vision.sent_at)}
                </span>
              </div>
              <p className={cn('whitespace-pre-wrap', VISION_TEXT_CLASS)}>{vision.body}</p>
            </article>
          ))}
        </TabsContent>

        <TabsContent value="relics" className="space-y-3">
          {(relics ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground">No relic yet.</p>
          )}
          {(relics ?? []).map((relic) => (
            <Card key={relic.id}>
              <CardContent className="py-4">
                <div className="font-semibold">{relic.item_name}</div>
                {relic.lore && <p className="text-sm text-muted-foreground">{relic.lore}</p>}
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="codex">
          <Card>
            <CardContent className="py-4">
              {(codex ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No Codex entry yet. Set a visibility on the edit page to create one.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr>
                      <th>Entry</th>
                      <th>Tier</th>
                      <th>Relation</th>
                      <th>Clues</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(codex ?? []).map((row) => (
                      <tr key={row.id} data-testid="codex-row">
                        <td className="font-medium">{row.name}</td>
                        <td>
                          <VisibilityBadge
                            visibility={tierOf(row.is_public, row.organizations)}
                            organizationName={row.organizations.join(', ')}
                          />
                        </td>
                        <td className="text-muted-foreground">{row.relation}</td>
                        <td>
                          {row.clues.length === 0 ? (
                            <span className="text-muted-foreground">
                              {row.is_public ? '' : 'no clue placed yet'}
                            </span>
                          ) : (
                            row.clues.map((slug) => (
                              <Badge key={slug} variant="outline" className="mr-1">
                                {slug}
                              </Badge>
                            ))
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
