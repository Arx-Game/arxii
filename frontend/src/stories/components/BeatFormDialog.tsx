/**
 * BeatFormDialog — create or edit a Beat within an Episode.
 *
 * The form's config section changes based on predicate_type selection.
 * Uses plain controlled state (not react-hook-form) to match project patterns.
 *
 * Predicate types and their config fields:
 *   gm_marked                  — no extra config
 *   character_level_at_least   — required_level (positive integer)
 *   achievement_held           — required_achievement (integer ID, manual entry)
 *   condition_held             — required_condition_template (integer ID, manual entry)
 *   codex_entry_unlocked       — required_codex_entry (integer ID, manual entry)
 *   story_at_milestone         — referenced_story + referenced_milestone_type + conditional chapter/episode
 *   aggregate_threshold        — required_points (positive integer)
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Combobox } from '@/components/ui/combobox';
import { EntitySearchField } from '@/components/EntitySearchField';
import { useAccount } from '@/store/hooks';
import { useGMProfileMine } from '@/gm/queries';
import {
  useSituationTemplateCatalog,
  useChallengeTemplateCatalog,
} from '@/gm-adjudication/queries';
import { useActiveCharacterId } from '@/gm-adjudication/useActiveCharacterId';
import { SituationFinder } from '@/gm-adjudication/SituationFinder';
import { getMissionTemplate, listMissionTemplates } from '@/missions/api';
import { OpponentLineDraft, OpponentLinesEditor } from './OpponentLinesEditor';
import { ConsequencePoolPicker } from './ConsequencePoolPicker';
import { StakesPanel } from './stakes/StakesPanel';
import {
  useCreateBeat,
  useUpdateBeat,
  useCreateBeatScenario,
  useStoryList,
  useChapterList,
  useEpisodeList,
  useBeatReadiness,
  useOpenBeatActivation,
} from '../queries';
import type {
  Beat,
  BeatCreateBody,
  BeatKind,
  BeatOpponentLine,
  BeatPredicateType,
  BeatRisk,
  BeatStagedTemplate,
  BeatVisibility,
  ReferencedMilestoneType,
} from '../types';
import { formSubmitLabel } from '../formSubmitLabel';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  episode?: string[];
  predicate_type?: string[];
  internal_description?: string[];
  player_hint?: string[];
  player_resolution_text?: string[];
  visibility?: string[];
  kind?: string[];
  advances?: string[];
  risk?: string[];
  order?: string[];
  deadline?: string[];
  agm_eligible?: string[];
  required_level?: string[];
  required_achievement?: string[];
  required_condition_template?: string[];
  required_codex_entry?: string[];
  referenced_story?: string[];
  referenced_milestone_type?: string[];
  referenced_chapter?: string[];
  referenced_episode?: string[];
  required_points?: string[];
  required_society?: string[];
  required_organization?: string[];
  required_standing?: string[];
  target_level?: string[];
  success_consequences?: string[];
  failure_consequences?: string[];
  expired_consequences?: string[];
  required_mission?: string[];
  non_field_errors?: string[];
  detail?: string;
  // #3425 session prep: DRF nested list-of-dicts field errors, one entry per
  // submitted row (empty object = that row is valid).
  opponent_lines?: Record<string, string[]>[];
  staged_templates?: Record<string, string[]>[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PREDICATE_OPTIONS: { value: BeatPredicateType; label: string }[] = [
  {
    value: 'outcome_tier',
    label: 'Outcome tier; resolved by the scenario, a fight, a battle or a decisive check',
  },
  { value: 'gm_marked', label: 'GM Marked; GM manually resolves this beat' },
  { value: 'character_level_at_least', label: 'Character Level At Least' },
  { value: 'achievement_held', label: 'Achievement Held' },
  { value: 'condition_held', label: 'Condition Held' },
  { value: 'codex_entry_unlocked', label: 'Codex Entry Unlocked' },
  { value: 'story_at_milestone', label: 'Story At Milestone' },
  { value: 'aggregate_threshold', label: 'Aggregate Threshold' },
  { value: 'faction_standing_at_least', label: 'Faction standing at least' },
];

const KIND_OPTIONS: { value: BeatKind; label: string }[] = [
  { value: 'situation', label: 'Situation' },
  { value: 'encounter', label: 'Encounter' },
  { value: 'task', label: 'Task' },
  { value: 'requirement', label: 'Requirement' },
];

/** SITUATION/TASK beats may carry a required_mission; other kinds never do. */
function kindHasRequiredMission(kind: BeatKind): boolean {
  return kind === 'situation' || kind === 'task';
}

const RISK_OPTIONS: { value: BeatRisk; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'low', label: 'Low' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'high', label: 'High' },
  { value: 'extreme', label: 'Extreme' },
];

// Mirrors the backend's RenownRisk ladder (`GMLevelCap.risk_index`, #3562):
// index into this array is how a viewer's cap ("up to moderate") and a
// beat's declared risk compare, without hand-rolling the comparison per site.
const RISK_LADDER: BeatRisk[] = ['none', 'low', 'moderate', 'high', 'extreme'];

function riskLabel(value: string): string {
  return RISK_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
}

/**
 * How far up `RISK_LADDER` the current viewer may set risk: staff top out
 * the ladder; a non-staff GM tops out at their `GMLevelCap.max_beat_risk`;
 * an account with no GM profile at all is capped to `none` (index 0) - the
 * caller separately disables the control entirely in that case via
 * `canSetRisk`, this index only governs which options render.
 */
function riskCapIndexFor(isStaff: boolean, maxBeatRisk: string | undefined): number {
  if (isStaff) return RISK_LADDER.length - 1;
  if (maxBeatRisk === undefined) return 0;
  return Math.max(0, RISK_LADDER.indexOf(maxBeatRisk as BeatRisk));
}

/** Caption under the risk select explaining the current cap (or its absence). */
function riskCaptionFor(isStaff: boolean, hasGMProfile: boolean, capIndex: number): string {
  if (isStaff) return 'Staff may set any risk';
  if (!hasGMProfile) return 'Only GMs may set risk';
  return `Your GM level allows up to ${riskLabel(RISK_LADDER[capIndex])}`;
}

const VISIBILITY_OPTIONS: { value: BeatVisibility; label: string }[] = [
  { value: 'hinted', label: 'Hinted; player sees a vague hint' },
  { value: 'visible', label: 'Visible; player sees full details' },
  { value: 'secret', label: 'Secret; player cannot see this beat' },
];

const MILESTONE_OPTIONS: { value: ReferencedMilestoneType; label: string }[] = [
  { value: 'story_resolved', label: 'Story Resolved' },
  { value: 'chapter_reached', label: 'Chapter Reached' },
  { value: 'episode_reached', label: 'Episode Reached' },
];

// ---------------------------------------------------------------------------
// Blank config state
// ---------------------------------------------------------------------------

/** Which side of the FACTION_STANDING_AT_LEAST XOR is currently authored. */
type FactionScope = 'society' | 'organization';

interface BeatConfig {
  required_level: string;
  required_achievement: string;
  required_condition_template: string;
  required_codex_entry: string;
  referenced_story: string;
  referenced_milestone_type: ReferencedMilestoneType;
  referenced_chapter: string;
  referenced_episode: string;
  required_points: string;
  faction_scope: FactionScope;
  required_society: string;
  required_organization: string;
  required_standing: string;
}

function blankConfig(): BeatConfig {
  return {
    required_level: '',
    required_achievement: '',
    required_condition_template: '',
    required_codex_entry: '',
    referenced_story: '',
    referenced_milestone_type: 'story_resolved',
    referenced_chapter: '',
    referenced_episode: '',
    required_points: '',
    faction_scope: 'society',
    required_society: '',
    required_organization: '',
    required_standing: '',
  };
}

/** Parse a numeric config string to a number, or null when blank. */
function numOrNull(value: string): number | null {
  return value ? Number(value) : null;
}

/**
 * Build the predicate-specific slice of a Beat payload from the current config.
 * Extracted from buildPayload to keep that function's cognitive complexity low.
 */
function predicateConfigPayload(
  predicateType: BeatPredicateType,
  config: BeatConfig
): Partial<BeatCreateBody> {
  switch (predicateType) {
    case 'character_level_at_least':
      return { required_level: numOrNull(config.required_level) };
    case 'achievement_held':
      return { required_achievement: numOrNull(config.required_achievement) };
    case 'condition_held':
      return { required_condition_template: numOrNull(config.required_condition_template) };
    case 'codex_entry_unlocked':
      return { required_codex_entry: numOrNull(config.required_codex_entry) };
    case 'story_at_milestone':
      return {
        referenced_story: numOrNull(config.referenced_story),
        referenced_milestone_type: config.referenced_milestone_type,
        referenced_chapter: numOrNull(config.referenced_chapter),
        referenced_episode: numOrNull(config.referenced_episode),
      };
    case 'aggregate_threshold':
      return { required_points: numOrNull(config.required_points) };
    case 'faction_standing_at_least':
      return config.faction_scope === 'organization'
        ? {
            required_society: null,
            required_organization: numOrNull(config.required_organization),
            required_standing: numOrNull(config.required_standing),
          }
        : {
            required_society: numOrNull(config.required_society),
            required_organization: null,
            required_standing: numOrNull(config.required_standing),
          };
    default:
      return {};
  }
}

function configFromBeat(beat: Beat): BeatConfig {
  return {
    required_level: beat.required_level != null ? String(beat.required_level) : '',
    required_achievement:
      beat.required_achievement != null ? String(beat.required_achievement) : '',
    required_condition_template:
      beat.required_condition_template != null ? String(beat.required_condition_template) : '',
    required_codex_entry:
      beat.required_codex_entry != null ? String(beat.required_codex_entry) : '',
    referenced_story: beat.referenced_story != null ? String(beat.referenced_story) : '',
    referenced_milestone_type:
      (beat.referenced_milestone_type as ReferencedMilestoneType) ?? 'story_resolved',
    referenced_chapter: beat.referenced_chapter != null ? String(beat.referenced_chapter) : '',
    referenced_episode: beat.referenced_episode != null ? String(beat.referenced_episode) : '',
    required_points: beat.required_points != null ? String(beat.required_points) : '',
    faction_scope: beat.required_organization != null ? 'organization' : 'society',
    required_society: beat.required_society != null ? String(beat.required_society) : '',
    required_organization:
      beat.required_organization != null ? String(beat.required_organization) : '',
    required_standing: beat.required_standing != null ? String(beat.required_standing) : '',
  };
}

// ---------------------------------------------------------------------------
// Predicate-specific config field(s)
// ---------------------------------------------------------------------------

interface ConfigFieldsProps {
  predicateType: BeatPredicateType;
  config: BeatConfig;
  onChange: (partial: Partial<BeatConfig>) => void;
  errors: DRFFieldErrors;
}

function PredicateConfigFields({ predicateType, config, onChange, errors }: ConfigFieldsProps) {
  // Fetch data for story-at-milestone conditional selectors
  const { data: storiesData } = useStoryList({ page_size: 100 });
  const storyOptions =
    storiesData?.results.map((s) => ({ value: String(s.id), label: s.title })) ?? [];

  const selectedStoryId = config.referenced_story ? Number(config.referenced_story) : undefined;
  const { data: chaptersData } = useChapterList(
    selectedStoryId !== undefined ? { story: selectedStoryId, page_size: 100 } : undefined
  );
  const chapterOptions =
    chaptersData?.results.map((c) => ({ value: String(c.id), label: c.title })) ?? [];

  const selectedChapterId = config.referenced_chapter
    ? Number(config.referenced_chapter)
    : undefined;
  const { data: episodesData } = useEpisodeList(
    selectedChapterId !== undefined ? { chapter: selectedChapterId, page_size: 100 } : undefined
  );
  const episodeOptions =
    episodesData?.results.map((ep) => ({ value: String(ep.id), label: ep.title })) ?? [];

  switch (predicateType) {
    case 'gm_marked':
      return null;

    case 'character_level_at_least':
      return (
        <div className="space-y-1.5">
          <Label htmlFor="beat-required-level">Required Level</Label>
          <Input
            id="beat-required-level"
            type="number"
            min={1}
            value={config.required_level}
            onChange={(e) => onChange({ required_level: e.target.value })}
            placeholder="e.g. 5"
          />
          {errors.required_level && (
            <p className="text-xs text-destructive">{errors.required_level.join(' ')}</p>
          )}
        </div>
      );

    case 'achievement_held':
      return (
        <div className="space-y-1.5">
          <Label htmlFor="beat-required-achievement">Required Achievement ID</Label>
          <Input
            id="beat-required-achievement"
            type="number"
            min={1}
            value={config.required_achievement}
            onChange={(e) => onChange({ required_achievement: e.target.value })}
            placeholder="Achievement ID"
          />
          {errors.required_achievement && (
            <p className="text-xs text-destructive">{errors.required_achievement.join(' ')}</p>
          )}
        </div>
      );

    case 'condition_held':
      return (
        <div className="space-y-1.5">
          <Label htmlFor="beat-required-condition">Required Condition Template ID</Label>
          <Input
            id="beat-required-condition"
            type="number"
            min={1}
            value={config.required_condition_template}
            onChange={(e) => onChange({ required_condition_template: e.target.value })}
            placeholder="Condition Template ID"
          />
          {errors.required_condition_template && (
            <p className="text-xs text-destructive">
              {errors.required_condition_template.join(' ')}
            </p>
          )}
        </div>
      );

    case 'codex_entry_unlocked':
      return (
        <div className="space-y-1.5">
          <Label htmlFor="beat-required-codex">Required Codex Entry ID</Label>
          <Input
            id="beat-required-codex"
            type="number"
            min={1}
            value={config.required_codex_entry}
            onChange={(e) => onChange({ required_codex_entry: e.target.value })}
            placeholder="Codex Entry ID"
          />
          {errors.required_codex_entry && (
            <p className="text-xs text-destructive">{errors.required_codex_entry.join(' ')}</p>
          )}
        </div>
      );

    case 'story_at_milestone': {
      const milestoneType = config.referenced_milestone_type;
      return (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Referenced Story</Label>
            <Combobox
              items={storyOptions}
              value={config.referenced_story}
              onValueChange={(val) =>
                onChange({ referenced_story: val, referenced_chapter: '', referenced_episode: '' })
              }
              placeholder="Select story…"
              searchPlaceholder="Search stories…"
              emptyMessage="No stories found."
            />
            {errors.referenced_story && (
              <p className="text-xs text-destructive">{errors.referenced_story.join(' ')}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label>Milestone Type</Label>
            <Combobox
              items={MILESTONE_OPTIONS}
              value={milestoneType}
              onValueChange={(val) =>
                onChange({
                  referenced_milestone_type: val as ReferencedMilestoneType,
                  referenced_chapter: '',
                  referenced_episode: '',
                })
              }
              placeholder="Select milestone type…"
            />
            {errors.referenced_milestone_type && (
              <p className="text-xs text-destructive">
                {errors.referenced_milestone_type.join(' ')}
              </p>
            )}
          </div>
          {milestoneType === 'chapter_reached' && (
            <div className="space-y-1.5">
              <Label>Referenced Chapter</Label>
              <Combobox
                items={chapterOptions}
                value={config.referenced_chapter}
                onValueChange={(val) =>
                  onChange({ referenced_chapter: val, referenced_episode: '' })
                }
                placeholder="Select chapter…"
                emptyMessage={
                  config.referenced_story ? 'No chapters found.' : 'Select a story first.'
                }
              />
              {errors.referenced_chapter && (
                <p className="text-xs text-destructive">{errors.referenced_chapter.join(' ')}</p>
              )}
            </div>
          )}
          {milestoneType === 'episode_reached' && (
            <>
              <div className="space-y-1.5">
                <Label>Referenced Chapter (for episode filter)</Label>
                <Combobox
                  items={chapterOptions}
                  value={config.referenced_chapter}
                  onValueChange={(val) =>
                    onChange({ referenced_chapter: val, referenced_episode: '' })
                  }
                  placeholder="Select chapter to filter episodes…"
                  emptyMessage={
                    config.referenced_story ? 'No chapters found.' : 'Select a story first.'
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label>Referenced Episode</Label>
                <Combobox
                  items={episodeOptions}
                  value={config.referenced_episode}
                  onValueChange={(val) => onChange({ referenced_episode: val })}
                  placeholder="Select episode…"
                  emptyMessage={
                    config.referenced_chapter ? 'No episodes found.' : 'Select a chapter first.'
                  }
                />
                {errors.referenced_episode && (
                  <p className="text-xs text-destructive">{errors.referenced_episode.join(' ')}</p>
                )}
              </div>
            </>
          )}
        </div>
      );
    }

    case 'aggregate_threshold':
      return (
        <div className="space-y-1.5">
          <Label htmlFor="beat-required-points">Required Points</Label>
          <Input
            id="beat-required-points"
            type="number"
            min={1}
            value={config.required_points}
            onChange={(e) => onChange({ required_points: e.target.value })}
            placeholder="e.g. 100"
          />
          {errors.required_points && (
            <p className="text-xs text-destructive">{errors.required_points.join(' ')}</p>
          )}
        </div>
      );

    case 'faction_standing_at_least': {
      const scope = config.faction_scope;
      return (
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Faction Type</Label>
            <RadioGroup
              value={scope}
              onValueChange={(val) => onChange({ faction_scope: val as FactionScope })}
              className="flex gap-4"
              data-testid="faction-scope-group"
            >
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <RadioGroupItem value="society" id="faction-scope-society" />
                <span>Society</span>
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <RadioGroupItem value="organization" id="faction-scope-organization" />
                <span>Organization</span>
              </label>
            </RadioGroup>
          </div>
          {scope === 'society' ? (
            <div className="space-y-1.5">
              <Label htmlFor="beat-required-society">Required Society ID</Label>
              <Input
                id="beat-required-society"
                type="number"
                min={1}
                value={config.required_society}
                onChange={(e) => onChange({ required_society: e.target.value })}
                placeholder="Society ID"
              />
              {errors.required_society && (
                <p className="text-xs text-destructive">{errors.required_society.join(' ')}</p>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="beat-required-organization">Required Organization ID</Label>
              <Input
                id="beat-required-organization"
                type="number"
                min={1}
                value={config.required_organization}
                onChange={(e) => onChange({ required_organization: e.target.value })}
                placeholder="Organization ID"
              />
              {errors.required_organization && (
                <p className="text-xs text-destructive">{errors.required_organization.join(' ')}</p>
              )}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="beat-required-standing">Required Standing</Label>
            <Input
              id="beat-required-standing"
              type="number"
              value={config.required_standing}
              onChange={(e) => onChange({ required_standing: e.target.value })}
              placeholder="e.g. 50"
            />
            {errors.required_standing && (
              <p className="text-xs text-destructive">{errors.required_standing.join(' ')}</p>
            )}
          </div>
        </div>
      );
    }

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Session prep row editors (#3425) — repeatable rows shown on kind=encounter
// (opponent lines) / kind=situation (staged situation/challenge templates).
// A row's `id` is carried through untouched when present (an existing row
// being edited) and omitted for a freshly-added row — BeatSerializer.update()
// diffs incoming rows against the beat's existing children by id.
// ---------------------------------------------------------------------------

function opponentLineDraftsFromBeat(beat: Beat | undefined): OpponentLineDraft[] {
  return (beat?.opponent_lines ?? []).map((line) => ({
    id: line.id,
    creature_template: String(line.creature_template),
    count: String(line.count ?? 1),
    position_name: line.position_name ?? '',
  }));
}

function opponentLineDraftsToPayload(drafts: OpponentLineDraft[]): BeatOpponentLine[] {
  return drafts
    .filter((d) => d.creature_template !== '')
    .map((d) => ({
      ...(d.id !== undefined ? { id: d.id } : {}),
      creature_template: Number(d.creature_template),
      count: d.count !== '' ? Number(d.count) : 1,
      position_name: d.position_name.trim(),
      order: 0,
    }));
}

/** Draft shape for one staged-template row while the form is open. */
interface StagedTemplateDraft {
  id?: number;
  templateKind: 'situation' | 'challenge';
  situation_template: string;
  challenge_template: string;
}

function stagedTemplateDraftsFromBeat(beat: Beat | undefined): StagedTemplateDraft[] {
  return (beat?.staged_templates ?? []).map((line) => {
    const situation = line.situation_template ?? null;
    const challenge = line.challenge_template ?? null;
    return {
      id: line.id,
      templateKind: situation !== null ? ('situation' as const) : ('challenge' as const),
      situation_template: situation !== null ? String(situation) : '',
      challenge_template: challenge !== null ? String(challenge) : '',
    };
  });
}

function stagedTemplateDraftsToPayload(drafts: StagedTemplateDraft[]): BeatStagedTemplate[] {
  return drafts
    .filter((d) =>
      d.templateKind === 'situation' ? d.situation_template !== '' : d.challenge_template !== ''
    )
    .map((d) => ({
      ...(d.id !== undefined ? { id: d.id } : {}),
      situation_template: d.templateKind === 'situation' ? Number(d.situation_template) : null,
      challenge_template: d.templateKind === 'challenge' ? Number(d.challenge_template) : null,
      order: 0,
    }));
}

interface StagedTemplatesEditorProps {
  lines: StagedTemplateDraft[];
  onChange: (lines: StagedTemplateDraft[]) => void;
  rowErrors: Record<string, string[]>[] | undefined;
  risk: BeatRisk;
}

function StagedTemplatesEditor({ lines, onChange, rowErrors, risk }: StagedTemplatesEditorProps) {
  const { data: situationTemplates = [] } = useSituationTemplateCatalog(true);
  const { data: challengeTemplates = [] } = useChallengeTemplateCatalog(true);
  const characterId = useActiveCharacterId();
  const [finderOpen, setFinderOpen] = useState(false);

  function updateRow(index: number, partial: Partial<StagedTemplateDraft>) {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...partial } : line)));
  }

  function addRow() {
    onChange([
      ...lines,
      { templateKind: 'situation', situation_template: '', challenge_template: '' },
    ]);
  }

  function removeRow(index: number) {
    onChange(lines.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2" data-testid="beat-staged-templates">
      <div className="flex items-center justify-between">
        <Label>Staging — situation/challenge templates</Label>
        <Button type="button" size="sm" variant="outline" onClick={addRow}>
          Add staged template
        </Button>
      </div>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        data-testid="finder-toggle"
        aria-expanded={finderOpen}
        onClick={() => setFinderOpen((v) => !v)}
      >
        {finderOpen ? 'Hide the catalog' : 'Browse the catalog'}
      </Button>
      {finderOpen && (
        <SituationFinder
          risk={risk === 'none' ? null : risk}
          characterId={characterId}
          actions={{
            template: {
              label: 'Stage',
              onSelect: (t) =>
                onChange([
                  ...lines,
                  {
                    templateKind: 'situation',
                    situation_template: String(t.id),
                    challenge_template: '',
                  },
                ]),
            },
            challenge: {
              label: 'Stage',
              onSelect: (c) =>
                onChange([
                  ...lines,
                  {
                    templateKind: 'challenge',
                    situation_template: '',
                    challenge_template: String(c.id),
                  },
                ]),
            },
          }}
        />
      )}
      {lines.length === 0 && (
        <p className="text-xs text-muted-foreground">No staging authored yet.</p>
      )}
      {lines.map((line, index) => {
        const errors = rowErrors?.[index];
        return (
          <div
            key={line.id ?? `new-${index}`}
            className="space-y-1 rounded-md border p-2"
            data-testid={`beat-staged-template-row-${index}`}
          >
            <div className="flex items-center gap-2">
              <select
                className="rounded-md border bg-background px-2 py-1.5 text-sm"
                value={line.templateKind}
                onChange={(e) =>
                  updateRow(index, { templateKind: e.target.value as 'situation' | 'challenge' })
                }
                data-testid={`beat-staged-template-kind-${index}`}
              >
                <option value="situation">Whole situation</option>
                <option value="challenge">Single challenge</option>
              </select>
              {line.templateKind === 'situation' ? (
                <select
                  className="flex-1 rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={line.situation_template}
                  onChange={(e) => updateRow(index, { situation_template: e.target.value })}
                  data-testid={`beat-staged-template-situation-${index}`}
                >
                  <option value="">Select a situation…</option>
                  {situationTemplates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  className="flex-1 rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={line.challenge_template}
                  onChange={(e) => updateRow(index, { challenge_template: e.target.value })}
                  data-testid={`beat-staged-template-challenge-${index}`}
                >
                  <option value="">Select a challenge…</option>
                  {challengeTemplates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              )}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => removeRow(index)}
                data-testid={`beat-staged-template-remove-${index}`}
              >
                Remove
              </Button>
            </div>
            {errors?.situation_template && (
              <p className="text-xs text-destructive">{errors.situation_template.join(' ')}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scenario section (#3565) - a SITUATION/TASK beat may run its own scenario
// graph instead of (or as well as) a catalog mission. Edit mode only: a
// scenario is minted against an existing beat id, so create mode just tells
// the author to save first.
// ---------------------------------------------------------------------------

const SCENARIO_RISK_TIER_OPTIONS = [1, 2, 3, 4, 5];

interface ScenarioSectionProps {
  beat: Beat | undefined;
}

function ScenarioSection({ beat }: ScenarioSectionProps) {
  const [designing, setDesigning] = useState(false);
  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [riskTier, setRiskTier] = useState('1');
  const [error, setError] = useState('');
  const [created, setCreated] = useState<{ template_id: number; name: string } | null>(null);
  const createScenario = useCreateBeatScenario();

  const scenario = created ?? beat?.scenario ?? null;

  if (!beat) {
    return (
      <div className="space-y-1.5" data-testid="beat-scenario-section">
        <Label>Scenario</Label>
        <p className="text-xs text-muted-foreground">Save the beat, then design its scenario.</p>
      </div>
    );
  }

  if (scenario != null) {
    return (
      <div className="space-y-1.5" data-testid="beat-scenario-section">
        <Label>Scenario</Label>
        <p className="text-sm">{scenario.name}</p>
        <Link
          to={`/stories/scenarios/${scenario.template_id}/canvas`}
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Open canvas
        </Link>
      </div>
    );
  }

  if (!designing) {
    return (
      <div className="space-y-1.5" data-testid="beat-scenario-section">
        <Label>Scenario</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setDesigning(true)}
          data-testid="design-scenario-btn"
        >
          Design scenario
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border p-3" data-testid="beat-scenario-section">
      <Label>Scenario</Label>
      <div className="space-y-1">
        <Label htmlFor="scenario-name" className="text-xs">
          Name
        </Label>
        <Input id="scenario-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="scenario-summary" className="text-xs">
          Summary
        </Label>
        <Textarea
          id="scenario-summary"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={2}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="scenario-risk-tier" className="text-xs">
          Risk tier
        </Label>
        <select
          id="scenario-risk-tier"
          value={riskTier}
          onChange={(e) => setRiskTier(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        >
          {SCENARIO_RISK_TIER_OPTIONS.map((tier) => (
            <option key={tier} value={tier}>
              {tier}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!name.trim() || createScenario.isPending}
          data-testid="confirm-design-scenario"
          onClick={() => {
            setError('');
            createScenario.mutate(
              {
                beatId: beat.id,
                name: name.trim(),
                summary: summary.trim(),
                risk_tier: Number(riskTier),
              },
              {
                onSuccess: (template) => {
                  toast.success('Scenario created');
                  setCreated({ template_id: template.id, name: template.name });
                  setDesigning(false);
                },
                onError: (err: unknown) => {
                  setError(err instanceof Error ? err.message : 'Failed to create scenario');
                },
              }
            );
          }}
        >
          Create
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setDesigning(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BeatFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  episodeId: number;
  beat?: Beat;
  onSuccess?: (beat: Beat) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BeatFormDialog({
  open,
  onOpenChange,
  episodeId,
  beat,
  onSuccess,
}: BeatFormDialogProps) {
  const isEdit = beat !== undefined;

  // Risk authoring is staff-gated server-side, or capped to a non-staff GM's
  // own GMLevelCap (`GMProfileMine.max_beat_risk`, #3562); the UI mirrors
  // both as defense-in-depth (the server remains the real boundary).
  const account = useAccount();
  const isStaff = account?.is_staff ?? false;
  const gmProfileQuery = useGMProfileMine();
  const gmProfile = gmProfileQuery.data;
  const hasGMProfile = gmProfile != null;
  const canSetRisk = isStaff || hasGMProfile;
  const riskCapIndex = riskCapIndexFor(isStaff, gmProfile?.max_beat_risk);

  // #3562 readiness dashboard + open stakes-contract-activation lock -
  // edit mode only (a beat must exist to have either).
  const readinessQuery = useBeatReadiness(beat?.id ?? -1, isEdit);
  const activationQuery = useOpenBeatActivation(beat?.id ?? -1, isEdit);
  const openActivation = activationQuery.data?.[0] ?? null;
  const isLocked = openActivation != null;

  const [predicateType, setPredicateType] = useState<BeatPredicateType>(
    beat?.predicate_type ?? 'outcome_tier'
  );
  const [config, setConfig] = useState<BeatConfig>(beat ? configFromBeat(beat) : blankConfig());
  const [internalDescription, setInternalDescription] = useState(beat?.internal_description ?? '');
  const [playerHint, setPlayerHint] = useState(beat?.player_hint ?? '');
  const [playerResolutionText, setPlayerResolutionText] = useState(
    beat?.player_resolution_text ?? ''
  );
  const [visibility, setVisibility] = useState<BeatVisibility>(beat?.visibility ?? 'hinted');
  const [kind, setKind] = useState<BeatKind>(beat?.kind ?? 'task');
  const [advances, setAdvances] = useState<boolean>(beat?.advances ?? true);
  const [risk, setRisk] = useState<BeatRisk>(beat?.risk ?? 'none');
  const [targetLevel, setTargetLevel] = useState<string>(
    beat?.target_level != null ? String(beat.target_level) : ''
  );
  const [successConsequences, setSuccessConsequences] = useState<number | null>(
    beat?.success_consequences ?? null
  );
  const [failureConsequences, setFailureConsequences] = useState<number | null>(
    beat?.failure_consequences ?? null
  );
  const [expiredConsequences, setExpiredConsequences] = useState<number | null>(
    beat?.expired_consequences ?? null
  );
  const [requiredMission, setRequiredMission] = useState<number | null>(
    beat?.required_mission ?? null
  );
  const [order, setOrder] = useState<string>(beat?.order !== undefined ? String(beat.order) : '');
  const [deadline, setDeadline] = useState(beat?.deadline ?? '');
  const [agmEligible, setAgmEligible] = useState(beat?.agm_eligible ?? false);
  const [opponentLines, setOpponentLines] = useState<OpponentLineDraft[]>(
    opponentLineDraftsFromBeat(beat)
  );
  const [stagedTemplates, setStagedTemplates] = useState<StagedTemplateDraft[]>(
    stagedTemplateDraftsFromBeat(beat)
  );
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  // Never hide an already-authored value the current viewer's cap wouldn't
  // let them newly select - show up to whichever is higher, cap or the
  // beat's existing risk, then rely on `disabled`/`canSetRisk` to stop a
  // capped viewer from moving it further.
  const riskVisibleMaxIndex = Math.max(riskCapIndex, RISK_LADDER.indexOf(risk));
  const riskOptionsToShow = canSetRisk
    ? RISK_OPTIONS.filter((opt) => RISK_LADDER.indexOf(opt.value) <= riskVisibleMaxIndex)
    : RISK_OPTIONS;
  const riskCaption = riskCaptionFor(isStaff, hasGMProfile, riskCapIndex);

  const createMutation = useCreateBeat();
  const updateMutation = useUpdateBeat();
  const isPending = createMutation.isPending || updateMutation.isPending;

  function handlePredicateTypeChange(newType: BeatPredicateType) {
    setPredicateType(newType);
    // Clear config fields when switching predicate type
    setConfig(blankConfig());
  }

  function handleConfigChange(partial: Partial<BeatConfig>) {
    setConfig((prev) => ({ ...prev, ...partial }));
  }

  function handleKindChange(newKind: BeatKind) {
    setKind(newKind);
    // required_mission only rides SITUATION/TASK beats (#3562) - clear it
    // when switching away so the picker's displayed state matches what
    // buildPayload() actually sends (never a silently-persisted stale FK).
    if (!kindHasRequiredMission(newKind)) setRequiredMission(null);
  }

  function resetForm() {
    setPredicateType(beat?.predicate_type ?? 'outcome_tier');
    setConfig(beat ? configFromBeat(beat) : blankConfig());
    setInternalDescription(beat?.internal_description ?? '');
    setPlayerHint(beat?.player_hint ?? '');
    setPlayerResolutionText(beat?.player_resolution_text ?? '');
    setVisibility(beat?.visibility ?? 'hinted');
    setKind(beat?.kind ?? 'task');
    setAdvances(beat?.advances ?? true);
    setRisk(beat?.risk ?? 'none');
    setTargetLevel(beat?.target_level != null ? String(beat.target_level) : '');
    setSuccessConsequences(beat?.success_consequences ?? null);
    setFailureConsequences(beat?.failure_consequences ?? null);
    setExpiredConsequences(beat?.expired_consequences ?? null);
    setRequiredMission(beat?.required_mission ?? null);
    setOrder(beat?.order !== undefined ? String(beat.order) : '');
    setDeadline(beat?.deadline ?? '');
    setAgmEligible(beat?.agm_eligible ?? false);
    setOpponentLines(opponentLineDraftsFromBeat(beat));
    setStagedTemplates(stagedTemplateDraftsFromBeat(beat));
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    onOpenChange(next);
  }

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') setFieldErrors(data as DRFFieldErrors);
          })
          .catch(() => toast.error('An error occurred. Please try again.'));
        return;
      }
    }
    toast.error(err instanceof Error ? err.message : 'An error occurred. Please try again.');
  }

  function buildPayload(): BeatCreateBody {
    const base: BeatCreateBody = {
      episode: episodeId,
      predicate_type: predicateType,
      internal_description: internalDescription.trim(),
      player_hint: playerHint.trim() || undefined,
      player_resolution_text: playerResolutionText.trim() || undefined,
      visibility,
      kind,
      advances,
      risk,
      target_level: targetLevel !== '' ? Number(targetLevel) : null,
      success_consequences: successConsequences,
      failure_consequences: failureConsequences,
      expired_consequences: expiredConsequences,
      required_mission: kindHasRequiredMission(kind) ? requiredMission : null,
      order: order !== '' ? Number(order) : undefined,
      deadline: deadline ? new Date(deadline).toISOString() : undefined,
      agm_eligible: agmEligible,
    };

    // #3425 session prep: only the section matching the current kind rides
    // the payload — switching kind away doesn't silently clear the other
    // kind's authored rows (they're simply left untouched server-side, since
    // an omitted nested-list field is a no-op on update, see
    // BeatSerializer.update()).
    const sessionPrep: Partial<BeatCreateBody> = {};
    if (kind === 'encounter') {
      sessionPrep.opponent_lines = opponentLineDraftsToPayload(opponentLines);
    } else if (kind === 'situation') {
      sessionPrep.staged_templates = stagedTemplateDraftsToPayload(stagedTemplates);
    }

    return {
      ...base,
      ...predicateConfigPayload(predicateType, config),
      ...sessionPrep,
    };
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    const payload = buildPayload();

    if (isEdit && beat) {
      updateMutation.mutate(
        { id: beat.id, data: payload },
        {
          onSuccess: (updated) => {
            toast.success('Beat updated');
            handleOpenChange(false);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(payload, {
        onSuccess: (created) => {
          toast.success('Beat created');
          handleOpenChange(false);
          onSuccess?.(created);
        },
        onError: handleError,
      });
    }
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? 'Edit Beat' : 'Create Beat'}</DialogTitle>
          </DialogHeader>

          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Predicate type */}
            <div className="space-y-2">
              <Label>Predicate Type</Label>
              <RadioGroup
                value={predicateType}
                onValueChange={(val) => handlePredicateTypeChange(val as BeatPredicateType)}
                className="flex flex-col gap-1"
                data-testid="predicate-type-group"
              >
                {PREDICATE_OPTIONS.map(({ value, label }) => (
                  <label
                    key={value}
                    className="flex cursor-pointer items-center gap-3 rounded-md border p-2.5 text-sm hover:bg-accent"
                  >
                    <RadioGroupItem value={value} id={`predicate-${value}`} />
                    <span>{label}</span>
                  </label>
                ))}
              </RadioGroup>
              {fieldErrors.predicate_type && (
                <p className="text-xs text-destructive">{fieldErrors.predicate_type.join(' ')}</p>
              )}
            </div>

            {/* Predicate-specific config */}
            <PredicateConfigFields
              predicateType={predicateType}
              config={config}
              onChange={handleConfigChange}
              errors={fieldErrors}
            />

            {/* Internal description */}
            <div className="space-y-1.5">
              <Label htmlFor="beat-internal-desc">
                Internal Description <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="beat-internal-desc"
                value={internalDescription}
                onChange={(e) => setInternalDescription(e.target.value)}
                placeholder="GM-only description of this beat…"
                rows={2}
                required
              />
              {fieldErrors.internal_description && (
                <p className="text-xs text-destructive">
                  {fieldErrors.internal_description.join(' ')}
                </p>
              )}
            </div>

            {/* Player hint */}
            <div className="space-y-1.5">
              <Label htmlFor="beat-player-hint">Player Hint</Label>
              <Input
                id="beat-player-hint"
                value={playerHint}
                onChange={(e) => setPlayerHint(e.target.value)}
                placeholder="What the player sees for hinted/visible beats…"
              />
              {fieldErrors.player_hint && (
                <p className="text-xs text-destructive">{fieldErrors.player_hint.join(' ')}</p>
              )}
            </div>

            {/* Player resolution text */}
            <div className="space-y-1.5">
              <Label htmlFor="beat-resolution-text">Player Resolution Text</Label>
              <Textarea
                id="beat-resolution-text"
                value={playerResolutionText}
                onChange={(e) => setPlayerResolutionText(e.target.value)}
                placeholder="Text shown to the player when this beat resolves…"
                rows={2}
              />
              {fieldErrors.player_resolution_text && (
                <p className="text-xs text-destructive">
                  {fieldErrors.player_resolution_text.join(' ')}
                </p>
              )}
            </div>

            {/* Visibility */}
            <div className="space-y-2">
              <Label>Visibility</Label>
              <RadioGroup
                value={visibility}
                onValueChange={(val) => setVisibility(val as BeatVisibility)}
                className="flex flex-col gap-1"
              >
                {VISIBILITY_OPTIONS.map(({ value, label }) => (
                  <label
                    key={value}
                    className="flex cursor-pointer items-center gap-3 rounded-md border p-2.5 text-sm hover:bg-accent"
                  >
                    <RadioGroupItem value={value} id={`visibility-${value}`} />
                    <span>{label}</span>
                  </label>
                ))}
              </RadioGroup>
              {fieldErrors.visibility && (
                <p className="text-xs text-destructive">{fieldErrors.visibility.join(' ')}</p>
              )}
            </div>

            {/* Kind */}
            <div className="space-y-1.5">
              <Label htmlFor="beat-kind">Kind</Label>
              <select
                id="beat-kind"
                value={kind}
                onChange={(e) => handleKindChange(e.target.value as BeatKind)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                {KIND_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              {fieldErrors.kind && (
                <p className="text-xs text-destructive">{fieldErrors.kind.join(' ')}</p>
              )}
            </div>

            {/* Session prep (#3425) — kind-gated repeatable rows */}
            {kind === 'encounter' && (
              <OpponentLinesEditor
                lines={opponentLines}
                onChange={setOpponentLines}
                rowErrors={fieldErrors.opponent_lines}
              />
            )}
            {kind === 'situation' && (
              <StagedTemplatesEditor
                lines={stagedTemplates}
                onChange={setStagedTemplates}
                rowErrors={fieldErrors.staged_templates}
                risk={risk}
              />
            )}

            {/* Required mission (#3562) - the catalog-mission alternative to
                the bespoke scenario graph below, for SITUATION/TASK beats. */}
            {kindHasRequiredMission(kind) && (
              <EntitySearchField
                label="Required mission"
                value={requiredMission}
                onChange={setRequiredMission}
                placeholder="Search mission templates…"
                search={async (query) => {
                  const res = await listMissionTemplates({ name: query, page_size: 20 });
                  return res.results.map((template) => ({
                    id: template.id,
                    name: template.name,
                    hint: template.story_id != null ? 'scenario' : `tier ${template.risk_tier}`,
                  }));
                }}
                resolveById={async (id) => {
                  const template = await getMissionTemplate(id);
                  return {
                    id: template.id,
                    name: template.name,
                    hint: template.story_id != null ? 'scenario' : `tier ${template.risk_tier}`,
                  };
                }}
              />
            )}
            {kindHasRequiredMission(kind) && fieldErrors.required_mission && (
              <p className="text-xs text-destructive">{fieldErrors.required_mission.join(' ')}</p>
            )}

            {/* Scenario graph (#3565) - a SITUATION/TASK beat's own body */}
            {(kind === 'situation' || kind === 'task') && <ScenarioSection beat={beat} />}

            {/* Stakes (#3561) - a stake is minted against an existing beat id, so
                create mode just tells the author to save first. */}
            {beat ? (
              <StakesPanel beat={beat} />
            ) : (
              <div className="space-y-1.5" data-testid="beat-stakes-section">
                <Label>Stakes</Label>
                <p className="text-xs text-muted-foreground">
                  Save the beat, then declare its stakes.
                </p>
              </div>
            )}

            {/* Readiness (#3562) - GM readiness dashboard, edit mode only. */}
            {isEdit && readinessQuery.data && (
              <div
                className="space-y-1 rounded-md border p-3 text-sm"
                data-testid="beat-readiness-strip"
              >
                <p className="font-medium">
                  {readinessQuery.data.is_ready ? 'Ready' : 'Not ready'}
                </p>
                {readinessQuery.data.problems.length > 0 && (
                  <ul className="list-disc space-y-0.5 pl-4 text-xs text-destructive">
                    {readinessQuery.data.problems.map((problem, i) => (
                      <li key={i}>{problem}</li>
                    ))}
                  </ul>
                )}
                {readinessQuery.data.advisories.length > 0 && (
                  <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                    {readinessQuery.data.advisories.map((advisory, i) => (
                      <li key={i}>{advisory}</li>
                    ))}
                  </ul>
                )}
                <p className="text-xs text-muted-foreground">
                  Effective risk for the table: {riskLabel(readinessQuery.data.effective_risk)}
                </p>
              </div>
            )}

            {/* Lock banner (#3562) - an open stakes-contract activation
                locks risk / target_level / the three consequence pools. */}
            {isEdit && openActivation && (
              <div
                className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm"
                data-testid="beat-lock-banner"
              >
                Locked while the scene runs (since {openActivation.locked_at})
              </div>
            )}

            {/* Advances */}
            <div className="space-y-1.5">
              <label className="flex cursor-pointer items-center gap-3 rounded-md border p-3">
                <input
                  type="checkbox"
                  checked={advances}
                  onChange={(e) => setAdvances(e.target.checked)}
                  className="h-4 w-4"
                  id="beat-advances"
                />
                <span className="text-sm">Advances the plot</span>
              </label>
              <p className="text-xs text-muted-foreground">
                Off = Tangent: recorded for history, never gates a transition
              </p>
              {fieldErrors.advances && (
                <p className="text-xs text-destructive">{fieldErrors.advances.join(' ')}</p>
              )}
            </div>

            {/* Risk and target level side-by-side (#3562) */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="beat-risk">Risk</Label>
                <select
                  id="beat-risk"
                  value={risk}
                  onChange={(e) => setRisk(e.target.value as BeatRisk)}
                  disabled={!canSetRisk || isLocked}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  {riskOptionsToShow.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">{riskCaption}</p>
                {fieldErrors.risk && (
                  <p className="text-xs text-destructive">{fieldErrors.risk.join(' ')}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="beat-target-level">Target Level</Label>
                <Input
                  id="beat-target-level"
                  type="number"
                  min={1}
                  value={targetLevel}
                  onChange={(e) => setTargetLevel(e.target.value)}
                  disabled={isLocked}
                  placeholder="e.g. 4"
                />
                {fieldErrors.target_level && (
                  <p className="text-xs text-destructive">{fieldErrors.target_level.join(' ')}</p>
                )}
              </div>
            </div>

            {/* Consequences (#3562) - the ConsequencePool that fires on each outcome. */}
            <div
              className="space-y-2 rounded-md border p-3"
              data-testid="beat-consequences-section"
            >
              <Label>Consequences</Label>
              <div className="grid gap-3 sm:grid-cols-3">
                <ConsequencePoolPicker
                  label="Success"
                  value={successConsequences}
                  onChange={setSuccessConsequences}
                  disabled={isLocked}
                />
                <ConsequencePoolPicker
                  label="Failure"
                  value={failureConsequences}
                  onChange={setFailureConsequences}
                  disabled={isLocked}
                />
                <ConsequencePoolPicker
                  label="Expired"
                  value={expiredConsequences}
                  onChange={setExpiredConsequences}
                  disabled={isLocked}
                />
              </div>
              {fieldErrors.success_consequences && (
                <p className="text-xs text-destructive">
                  {fieldErrors.success_consequences.join(' ')}
                </p>
              )}
              {fieldErrors.failure_consequences && (
                <p className="text-xs text-destructive">
                  {fieldErrors.failure_consequences.join(' ')}
                </p>
              )}
              {fieldErrors.expired_consequences && (
                <p className="text-xs text-destructive">
                  {fieldErrors.expired_consequences.join(' ')}
                </p>
              )}
            </div>

            {/* Order and deadline side-by-side */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="beat-order">Order</Label>
                <Input
                  id="beat-order"
                  type="number"
                  min={0}
                  value={order}
                  onChange={(e) => setOrder(e.target.value)}
                  placeholder="e.g. 1"
                />
                {fieldErrors.order && (
                  <p className="text-xs text-destructive">{fieldErrors.order.join(' ')}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="beat-deadline">Deadline (optional)</Label>
                <Input
                  id="beat-deadline"
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
                {fieldErrors.deadline && (
                  <p className="text-xs text-destructive">{fieldErrors.deadline.join(' ')}</p>
                )}
              </div>
            </div>

            {/* AGM eligible */}
            <label className="flex cursor-pointer items-center gap-3 rounded-md border p-3">
              <input
                type="checkbox"
                checked={agmEligible}
                onChange={(e) => setAgmEligible(e.target.checked)}
                className="h-4 w-4"
                id="beat-agm-eligible"
              />
              <span className="text-sm">AGM eligible: allow Assistant GMs to claim this beat</span>
            </label>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {formSubmitLabel(isPending, isEdit, 'Beat')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
