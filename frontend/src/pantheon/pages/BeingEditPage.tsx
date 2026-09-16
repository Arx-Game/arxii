/**
 * The edit page (#3780): one long page, never a wizard. Every section is collapsible and
 * carries a highlight dot while an optional field is unfilled. No explainer copy; each
 * "+ Add" carries its explanation as a hover tooltip. Save is live at once: there is no
 * draft gate pre-launch. Blank fields simply do not render on the Codex.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Accordion } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { EditorSection } from '../components/EditorSection';
import { VISIBILITY_LABELS } from '../visibility';
import { useBeingPage, useEditorOptions, useSaveBeing } from '../queries';
import type {
  EditorOptions,
  FeastDayLine,
  RelationshipLineWithName,
  ResonanceLineWithName,
  StaffBeingPage,
  StaffBeingPageRequest,
  Visibility,
} from '../types';

const RESONANCE_TIERS = [
  { value: 'favored', label: 'Favored (2×)' },
  { value: 'associated', label: 'Associated (1×)' },
];
const VALENCES = [
  { value: 'ally', label: 'Allies with' },
  { value: 'rival', label: 'Rivals' },
  { value: 'feud', label: 'Feuds with' },
];
const VISIBILITY_HINTS: Record<Visibility, string> = {
  public: 'Known to the entire game.',
  obscure: 'Known within one organization.',
  secret: 'Researchable only: a Clue must be found first.',
};

interface Draft {
  name: string;
  description: string;
  domains: string;
  tradition: string;
  is_active: boolean;
  quote: string;
  nicknames: string[];
  resonances: ResonanceLineWithName[];
  facets: number[];
  feast_days: FeastDayLine[];
  tarot_cards: number[];
  relationships: RelationshipLineWithName[];
  visibility: Visibility;
  organization: string;
  gm_notes: string;
}

const EMPTY: Draft = {
  name: '',
  description: '',
  domains: '',
  tradition: '',
  is_active: true,
  quote: '',
  nicknames: [],
  resonances: [],
  facets: [],
  feast_days: [],
  tarot_cards: [],
  relationships: [],
  visibility: 'secret',
  organization: '',
  gm_notes: '',
};

function draftFrom(page: StaffBeingPage): Draft {
  return {
    name: page.name,
    description: page.description ?? '',
    domains: page.domains ?? '',
    tradition: String(page.tradition),
    is_active: page.is_active ?? true,
    quote: page.quote ?? '',
    nicknames: page.nicknames ?? [],
    resonances: (page.resonances ?? []) as ResonanceLineWithName[],
    facets: page.facets ?? [],
    feast_days: page.feast_days ?? [],
    tarot_cards: page.tarot_cards ?? [],
    relationships: (page.relationships ?? []) as RelationshipLineWithName[],
    visibility: (page.visibility ?? 'secret') as Visibility,
    organization: page.organization ? String(page.organization) : '',
    gm_notes: page.gm_notes ?? '',
  };
}

function toRequest(draft: Draft): StaffBeingPageRequest {
  return {
    name: draft.name.trim(),
    description: draft.description,
    domains: draft.domains,
    tradition: Number(draft.tradition),
    is_active: draft.is_active,
    quote: draft.quote,
    nicknames: draft.nicknames.map((n) => n.trim()).filter(Boolean),
    resonances: draft.resonances.map(({ resonance, tier }) => ({ resonance, tier })),
    facets: draft.facets,
    feast_days: draft.feast_days.filter((day) => day.name.trim()),
    tarot_cards: draft.tarot_cards,
    relationships: draft.relationships.map(({ other_being, valence, public_story }) => ({
      other_being,
      valence,
      public_story: public_story ?? '',
    })),
    visibility: draft.visibility,
    organization:
      draft.visibility === 'obscure' && draft.organization ? Number(draft.organization) : null,
    gm_notes: draft.gm_notes,
  };
}

function nameOf(refs: { id: number; name: string }[] | undefined, id: number): string {
  return refs?.find((ref) => ref.id === id)?.name ?? `#${id}`;
}

/** A picker that adds one id to a list, then clears. */
function AddPicker({
  items,
  label,
  onPick,
  hint,
}: {
  items: { value: string; label: string }[];
  label: string;
  onPick: (id: number) => void;
  hint: string;
}) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <Button type="button" variant="outline" size="sm" title={hint} onClick={() => setOpen(true)}>
        + {label}
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <Combobox
        items={items}
        value=""
        onValueChange={(value) => {
          if (value) onPick(Number(value));
          setOpen(false);
        }}
        placeholder={label}
        className="w-64"
      />
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
        Cancel
      </Button>
    </div>
  );
}

export function BeingEditPage() {
  const { id } = useParams<{ id: string }>();
  const beingId = id ? Number(id) : null;
  const navigate = useNavigate();
  const { data: page, isLoading } = useBeingPage(beingId);
  const { data: options } = useEditorOptions();
  const save = useSaveBeing(beingId);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loadedFor, setLoadedFor] = useState<number | null>(null);

  useEffect(() => {
    if (page && loadedFor !== page.id) {
      setDraft(draftFrom(page));
      setLoadedFor(page.id);
    }
  }, [page, loadedFor]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const refItems = (refs: { id: number; name: string }[] | undefined, exclude: number[] = []) =>
    (refs ?? [])
      .filter((ref) => !exclude.includes(ref.id))
      .map((ref) => ({ value: String(ref.id), label: ref.name }));

  const incomplete = useMemo(
    () => ({
      identity: !draft.description.trim() || !draft.quote.trim(),
      nicknames: draft.nicknames.length === 0,
      portfolio: !draft.domains.trim() || draft.resonances.length === 0,
      feast: draft.feast_days.length === 0,
      tarot: draft.tarot_cards.length === 0,
      relationships: draft.relationships.length === 0,
      visibility: draft.visibility === 'obscure' && !draft.organization,
      notes: !draft.gm_notes.trim(),
    }),
    [draft]
  );

  function handleSave() {
    if (!draft.name.trim()) {
      toast.error('A god needs a name.');
      return;
    }
    if (!draft.tradition) {
      toast.error('Pick the tradition.');
      return;
    }
    if (draft.visibility === 'obscure' && !draft.organization) {
      toast.error('An obscure god is known to one organization: pick it.');
      return;
    }
    save.mutate(toRequest(draft), {
      onSuccess: (saved) => {
        toast.success(`${saved.name} saved. Live now.`);
        navigate(`/staff/pantheon/${saved.id}`);
      },
      onError: (error: Error) => toast.error(error.message),
    });
  }

  if (beingId !== null && isLoading) {
    return <p className="container mx-auto max-w-6xl px-4 py-8 text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link to="/staff/pantheon" className="text-xs text-muted-foreground hover:underline">
            ← Deity Editor
          </Link>
          <h1 className="text-2xl font-bold">
            {beingId === null ? 'New god' : `Editing: ${page?.name ?? ''}`}
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">Live the moment you save.</span>
          <Button onClick={handleSave} disabled={save.isPending} data-testid="save-top">
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>

      <Accordion
        type="multiple"
        defaultValue={['identity', 'portfolio', 'visibility']}
        className="space-y-3"
      >
        <EditorSection value="identity" title="Identity" incomplete={incomplete.identity}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="god-name">Name</Label>
              <Input
                id="god-name"
                value={draft.name}
                onChange={(e) => set('name', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="god-tradition">Tradition</Label>
              <Select value={draft.tradition} onValueChange={(v) => set('tradition', v)}>
                <SelectTrigger id="god-tradition">
                  <SelectValue placeholder="Pick a tradition" />
                </SelectTrigger>
                <SelectContent>
                  {(options?.traditions ?? []).map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="god-description">Description</Label>
            <Textarea
              id="god-description"
              rows={4}
              value={draft.description}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="god-quote">Quote</Label>
            <Input
              id="god-quote"
              value={draft.quote}
              maxLength={300}
              onChange={(e) => set('quote', e.target.value)}
              title="An italic line atop the Codex page; blank hides it."
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="god-active"
              checked={draft.is_active}
              onCheckedChange={(v) => set('is_active', v)}
            />
            <Label htmlFor="god-active">Active (worshippable)</Label>
          </div>
        </EditorSection>

        <EditorSection value="nicknames" title="Nicknames" incomplete={incomplete.nicknames}>
          {draft.nicknames.map((nickname, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                value={nickname}
                aria-label={`Nickname ${index + 1}`}
                onChange={(e) =>
                  set(
                    'nicknames',
                    draft.nicknames.map((n, i) => (i === index ? e.target.value : n))
                  )
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label="Remove nickname"
                onClick={() =>
                  set(
                    'nicknames',
                    draft.nicknames.filter((_, i) => i !== index)
                  )
                }
              >
                ×
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            title="An alternate name worshippers use; a house's patron shows its own nickname on its sheet."
            onClick={() => set('nicknames', [...draft.nicknames, ''])}
          >
            + Add nickname
          </Button>
        </EditorSection>

        <EditorSection value="portfolio" title="Portfolio" incomplete={incomplete.portfolio}>
          <div className="space-y-1">
            <Label htmlFor="god-domains">Spheres / domains</Label>
            <Input
              id="god-domains"
              value={draft.domains}
              onChange={(e) => set('domains', e.target.value)}
              title="Plain text, comma-separated; overlap with other gods is fine."
            />
          </div>
          <div className="space-y-2">
            <Label>Resonance</Label>
            <div className="flex flex-wrap items-center gap-2">
              {draft.resonances.map((line) => (
                <Badge
                  key={line.resonance}
                  variant={line.tier === 'favored' ? 'default' : 'secondary'}
                >
                  {line.resonance_name ?? nameOf(options?.resonances, line.resonance)} ·{' '}
                  {line.tier === 'favored' ? 'Favored (2×)' : 'Associated (1×)'}
                  <button
                    type="button"
                    className="ml-2"
                    aria-label={`Remove ${line.resonance_name ?? ''} resonance`}
                    onClick={() =>
                      set(
                        'resonances',
                        draft.resonances.filter((r) => r.resonance !== line.resonance)
                      )
                    }
                  >
                    ×
                  </button>
                </Badge>
              ))}
              <AddResonance
                options={options}
                exclude={draft.resonances.map((r) => r.resonance)}
                onAdd={(line) => set('resonances', [...draft.resonances, line])}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Favored facets</Label>
            <div className="flex flex-wrap items-center gap-2">
              {draft.facets.map((facetId) => (
                <Badge key={facetId} variant="secondary">
                  {nameOf(options?.facets, facetId)}
                  <button
                    type="button"
                    className="ml-2"
                    aria-label="Remove facet"
                    onClick={() =>
                      set(
                        'facets',
                        draft.facets.filter((f) => f !== facetId)
                      )
                    }
                  >
                    ×
                  </button>
                </Badge>
              ))}
              <AddPicker
                items={refItems(options?.facets, draft.facets)}
                label="Add facet"
                hint="An aesthetic facet the being favors; an offered item carrying it is credited double."
                onPick={(facetId) => set('facets', [...draft.facets, facetId])}
              />
            </div>
          </div>
        </EditorSection>

        <EditorSection value="feast" title="Feast Days" incomplete={incomplete.feast}>
          {draft.feast_days.map((day, index) => (
            <div
              key={index}
              className="grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_5rem_5rem_auto]"
            >
              <Input
                value={day.name}
                aria-label={`Feast day ${index + 1} name`}
                placeholder="Name"
                onChange={(e) =>
                  set(
                    'feast_days',
                    draft.feast_days.map((d, i) =>
                      i === index ? { ...d, name: e.target.value } : d
                    )
                  )
                }
              />
              <Input
                type="number"
                min={1}
                max={12}
                value={day.ic_month}
                aria-label="Month"
                onChange={(e) =>
                  set(
                    'feast_days',
                    draft.feast_days.map((d, i) =>
                      i === index ? { ...d, ic_month: Number(e.target.value) } : d
                    )
                  )
                }
              />
              <Input
                type="number"
                min={1}
                max={31}
                value={day.ic_day}
                aria-label="Day"
                onChange={(e) =>
                  set(
                    'feast_days',
                    draft.feast_days.map((d, i) =>
                      i === index ? { ...d, ic_day: Number(e.target.value) } : d
                    )
                  )
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label="Remove feast day"
                onClick={() =>
                  set(
                    'feast_days',
                    draft.feast_days.filter((_, i) => i !== index)
                  )
                }
              >
                ×
              </Button>
              <Textarea
                className="sm:col-span-4"
                rows={2}
                placeholder="Lore"
                value={day.lore ?? ''}
                onChange={(e) =>
                  set(
                    'feast_days',
                    draft.feast_days.map((d, i) =>
                      i === index ? { ...d, lore: e.target.value } : d
                    )
                  )
                }
              />
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            title="An IC month and day, every year; worship for the being that day pays double."
            onClick={() =>
              set('feast_days', [
                ...draft.feast_days,
                { ic_month: 1, ic_day: 1, name: '', lore: '' },
              ])
            }
          >
            + Add feast day
          </Button>
        </EditorSection>

        <EditorSection value="tarot" title="Tarot" incomplete={incomplete.tarot}>
          <div className="flex flex-wrap items-center gap-2">
            {draft.tarot_cards.map((cardId) => (
              <Badge key={cardId} variant="secondary">
                {nameOf(options?.tarot_cards, cardId)}
                <button
                  type="button"
                  className="ml-2"
                  aria-label="Remove card"
                  onClick={() =>
                    set(
                      'tarot_cards',
                      draft.tarot_cards.filter((c) => c !== cardId)
                    )
                  }
                >
                  ×
                </button>
              </Badge>
            ))}
            <AddPicker
              items={refItems(options?.tarot_cards, draft.tarot_cards)}
              label="Add card"
              hint="Cards people believe represent the being; empty hides Tarot from the Codex."
              onPick={(cardId) => set('tarot_cards', [...draft.tarot_cards, cardId])}
            />
          </div>
        </EditorSection>

        <EditorSection
          value="relationships"
          title="Relationships"
          incomplete={incomplete.relationships}
        >
          {draft.relationships.map((line, index) => (
            <div key={line.other_being} className="space-y-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={line.valence}
                  onValueChange={(v) =>
                    set(
                      'relationships',
                      draft.relationships.map((r, i) =>
                        i === index ? { ...r, valence: v as never } : r
                      )
                    )
                  }
                >
                  <SelectTrigger className="w-40" aria-label="Valence">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VALENCES.map((v) => (
                      <SelectItem key={v.value} value={v.value}>
                        {v.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <span className="font-medium">
                  {line.other_being_name ?? nameOf(options?.beings, line.other_being)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  aria-label="Remove relationship"
                  onClick={() =>
                    set(
                      'relationships',
                      draft.relationships.filter((_, i) => i !== index)
                    )
                  }
                >
                  ×
                </Button>
              </div>
              <Textarea
                rows={2}
                placeholder="Public story shown on the Codex"
                value={line.public_story ?? ''}
                onChange={(e) =>
                  set(
                    'relationships',
                    draft.relationships.map((r, i) =>
                      i === index ? { ...r, public_story: e.target.value } : r
                    )
                  )
                }
              />
            </div>
          ))}
          <AddPicker
            items={refItems(
              options?.beings?.filter((b) => b.id !== beingId),
              draft.relationships.map((r) => r.other_being)
            )}
            label="Add relationship"
            hint="A public relationship with another god; renders as a line on the Codex linking to them."
            onPick={(otherId) =>
              set('relationships', [
                ...draft.relationships,
                { other_being: otherId, valence: 'ally', public_story: '' },
              ])
            }
          />
        </EditorSection>

        <EditorSection value="visibility" title="Visibility" incomplete={incomplete.visibility}>
          <div className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Visibility">
            {(Object.keys(VISIBILITY_LABELS) as Visibility[]).map((tier) => (
              <button
                key={tier}
                type="button"
                role="radio"
                aria-checked={draft.visibility === tier}
                data-testid={`visibility-${tier}`}
                title={VISIBILITY_HINTS[tier]}
                onClick={() => set('visibility', tier)}
                className={cn(
                  'rounded-md border p-3 text-left transition-colors hover:bg-muted/50',
                  draft.visibility === tier && 'border-foreground bg-muted'
                )}
              >
                <div className="font-semibold">{VISIBILITY_LABELS[tier]}</div>
              </button>
            ))}
          </div>
          {draft.visibility === 'obscure' && (
            <div className="space-y-1">
              <Label>Known to</Label>
              <Combobox
                items={refItems(options?.organizations)}
                value={draft.organization}
                onValueChange={(v) => set('organization', v)}
                placeholder="Pick the organization"
                className="w-full max-w-md"
              />
            </div>
          )}
        </EditorSection>

        <EditorSection value="notes" title="GM Notes" incomplete={incomplete.notes} tint="gm">
          <Textarea
            rows={5}
            value={draft.gm_notes}
            aria-label="GM notes"
            onChange={(e) => set('gm_notes', e.target.value)}
            title="Staff only, never shown to players: continuity, who this was in Arx 1."
          />
        </EditorSection>
      </Accordion>

      <div className="mt-6 flex justify-end">
        <Button onClick={handleSave} disabled={save.isPending} data-testid="save-bottom">
          {save.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}

function AddResonance({
  options,
  exclude,
  onAdd,
}: {
  options: EditorOptions | undefined;
  exclude: number[];
  onAdd: (line: ResonanceLineWithName) => void;
}) {
  const [open, setOpen] = useState(false);
  const [resonance, setResonance] = useState('');
  const [tier, setTier] = useState('favored');
  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        title="A resonance the being favors (acts in its name pay double) or is merely associated with."
        onClick={() => setOpen(true)}
      >
        + Add resonance
      </Button>
    );
  }
  const items = (options?.resonances ?? [])
    .filter((ref) => !exclude.includes(ref.id))
    .map((ref) => ({ value: String(ref.id), label: ref.name }));
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Combobox
        items={items}
        value={resonance}
        onValueChange={setResonance}
        placeholder="Resonance"
        className="w-56"
      />
      <Select value={tier} onValueChange={setTier}>
        <SelectTrigger className="w-40" aria-label="Tier">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {RESONANCE_TIERS.map((t) => (
            <SelectItem key={t.value} value={t.value}>
              {t.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        size="sm"
        disabled={!resonance}
        onClick={() => {
          onAdd({
            resonance: Number(resonance),
            resonance_name: options?.resonances.find((r) => r.id === Number(resonance))?.name,
            tier: tier as never,
          });
          setResonance('');
          setOpen(false);
        }}
      >
        Add
      </Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
        Cancel
      </Button>
    </div>
  );
}
