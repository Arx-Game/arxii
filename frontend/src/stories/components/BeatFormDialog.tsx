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
import {
  useCreateBeat,
  useUpdateBeat,
  useStoryList,
  useChapterList,
  useEpisodeList,
} from '../queries';
import type { Beat, BeatPredicateType, BeatVisibility, ReferencedMilestoneType } from '../types';

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
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PREDICATE_OPTIONS: { value: BeatPredicateType; label: string }[] = [
  { value: 'gm_marked', label: 'GM Marked — GM manually resolves this beat' },
  { value: 'character_level_at_least', label: 'Character Level At Least' },
  { value: 'achievement_held', label: 'Achievement Held' },
  { value: 'condition_held', label: 'Condition Held' },
  { value: 'codex_entry_unlocked', label: 'Codex Entry Unlocked' },
  { value: 'story_at_milestone', label: 'Story At Milestone' },
  { value: 'aggregate_threshold', label: 'Aggregate Threshold' },
];

const VISIBILITY_OPTIONS: { value: BeatVisibility; label: string }[] = [
  { value: 'hinted', label: 'Hinted — player sees a vague hint' },
  { value: 'visible', label: 'Visible — player sees full details' },
  { value: 'secret', label: 'Secret — player cannot see this beat' },
];

const MILESTONE_OPTIONS: { value: ReferencedMilestoneType; label: string }[] = [
  { value: 'story_resolved', label: 'Story Resolved' },
  { value: 'chapter_reached', label: 'Chapter Reached' },
  { value: 'episode_reached', label: 'Episode Reached' },
];

// ---------------------------------------------------------------------------
// Blank config state
// ---------------------------------------------------------------------------

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
  };
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

    default:
      return null;
  }
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

  const [predicateType, setPredicateType] = useState<BeatPredicateType>(
    beat?.predicate_type ?? 'gm_marked'
  );
  const [config, setConfig] = useState<BeatConfig>(beat ? configFromBeat(beat) : blankConfig());
  const [internalDescription, setInternalDescription] = useState(beat?.internal_description ?? '');
  const [playerHint, setPlayerHint] = useState(beat?.player_hint ?? '');
  const [playerResolutionText, setPlayerResolutionText] = useState(
    beat?.player_resolution_text ?? ''
  );
  const [visibility, setVisibility] = useState<BeatVisibility>(beat?.visibility ?? 'hinted');
  const [order, setOrder] = useState<string>(beat?.order !== undefined ? String(beat.order) : '');
  const [deadline, setDeadline] = useState(beat?.deadline ?? '');
  const [agmEligible, setAgmEligible] = useState(beat?.agm_eligible ?? false);
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

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

  function resetForm() {
    setPredicateType(beat?.predicate_type ?? 'gm_marked');
    setConfig(beat ? configFromBeat(beat) : blankConfig());
    setInternalDescription(beat?.internal_description ?? '');
    setPlayerHint(beat?.player_hint ?? '');
    setPlayerResolutionText(beat?.player_resolution_text ?? '');
    setVisibility(beat?.visibility ?? 'hinted');
    setOrder(beat?.order !== undefined ? String(beat.order) : '');
    setDeadline(beat?.deadline ?? '');
    setAgmEligible(beat?.agm_eligible ?? false);
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

  function buildPayload(): Partial<Beat> {
    const base: Partial<Beat> = {
      episode: episodeId,
      predicate_type: predicateType,
      internal_description: internalDescription.trim(),
      player_hint: playerHint.trim() || undefined,
      player_resolution_text: playerResolutionText.trim() || undefined,
      visibility,
      order: order !== '' ? Number(order) : undefined,
      deadline: deadline || undefined,
      agm_eligible: agmEligible,
    };

    // Predicate-specific config
    switch (predicateType) {
      case 'character_level_at_least':
        base.required_level = config.required_level ? Number(config.required_level) : null;
        break;
      case 'achievement_held':
        base.required_achievement = config.required_achievement
          ? Number(config.required_achievement)
          : null;
        break;
      case 'condition_held':
        base.required_condition_template = config.required_condition_template
          ? Number(config.required_condition_template)
          : null;
        break;
      case 'codex_entry_unlocked':
        base.required_codex_entry = config.required_codex_entry
          ? Number(config.required_codex_entry)
          : null;
        break;
      case 'story_at_milestone':
        base.referenced_story = config.referenced_story ? Number(config.referenced_story) : null;
        base.referenced_milestone_type = config.referenced_milestone_type;
        base.referenced_chapter = config.referenced_chapter
          ? Number(config.referenced_chapter)
          : null;
        base.referenced_episode = config.referenced_episode
          ? Number(config.referenced_episode)
          : null;
        break;
      case 'aggregate_threshold':
        base.required_points = config.required_points ? Number(config.required_points) : null;
        break;
      default:
        break;
    }

    return base;
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
              <span className="text-sm">AGM eligible — allow Assistant GMs to claim this beat</span>
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
              {isPending
                ? isEdit
                  ? 'Saving…'
                  : 'Creating…'
                : isEdit
                  ? 'Save Beat'
                  : 'Create Beat'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
