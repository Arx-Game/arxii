/**
 * Stage 8: Review & Submit
 *
 * Final review of character sheet with validation summary.
 * Submit button for players, "Add to Roster" button for staff/GM.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { AlertCircle, Send, UserPlus } from 'lucide-react';
import { useAddToRoster, useSubmitDraft } from '../queries';
import type { CharacterDraft } from '../types';
import { Stage, STAGE_LABELS } from '../types';

interface ReviewStageProps {
  draft: CharacterDraft;
  isStaff: boolean;
  onStageSelect: (stage: Stage) => void;
}

export function ReviewStage({ draft, isStaff, onStageSelect }: ReviewStageProps) {
  const submitDraft = useSubmitDraft();
  const addToRoster = useAddToRoster();

  const stageCompletion = draft.stage_completion;
  const incompleteStages = Object.entries(stageCompletion)
    .filter(([stage, complete]) => !complete && parseInt(stage) !== Stage.REVIEW)
    .map(([stage]) => parseInt(stage) as Stage);

  const canSubmit = incompleteStages.length === 0;
  const draftData = draft.draft_data;
  const familyName = draft.family?.name ?? draft.selected_heritage?.family_display ?? '';
  const fullName = draftData.first_name
    ? familyName
      ? `${draftData.first_name} ${familyName}`
      : draftData.first_name
    : 'Unnamed Character';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">Review & Submit</h2>
        <p className="mt-2 text-muted-foreground">
          Review your character before submitting for approval.
        </p>
      </div>

      {/* Validation Summary */}
      {incompleteStages.length > 0 && (
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-yellow-500" />
              <CardTitle className="text-base">Incomplete Sections</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="mb-3 text-sm text-muted-foreground">
              Please complete these sections before submitting:
            </p>
            <ul className="space-y-1">
              {incompleteStages.map((stage) => (
                <li key={stage}>
                  <button
                    onClick={() => onStageSelect(stage)}
                    className="text-sm text-primary underline-offset-4 hover:underline"
                  >
                    {STAGE_LABELS[stage]}
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Character Sheet Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{fullName}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Basic Info */}
          <section className="grid gap-4 sm:grid-cols-2">
            <InfoRow label="Homeland" value={draft.selected_area?.name} />
            <InfoRow
              label="Heritage"
              value={draft.selected_heritage?.name ?? 'Normal Upbringing'}
            />
            <InfoRow label="Species" value={draft.species} />
            <InfoRow
              label="Gender"
              value={
                draft.gender
                  ? draft.gender.charAt(0).toUpperCase() + draft.gender.slice(1)
                  : undefined
              }
            />
            <InfoRow label="Age" value={draft.age?.toString()} />
          </section>

          <Separator />

          {/* Lineage */}
          <section>
            <h4 className="mb-2 font-semibold">Lineage</h4>
            <InfoRow
              label="Family"
              value={
                draft.is_orphan
                  ? 'Orphan / No Family'
                  : (draft.family?.name ?? draft.selected_heritage?.family_display)
              }
            />
          </section>

          {draftData.description && (
            <>
              <Separator />
              <section>
                <h4 className="mb-2 font-semibold">Description</h4>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {draftData.description}
                </p>
              </section>
            </>
          )}

          {draftData.personality && (
            <>
              <Separator />
              <section>
                <h4 className="mb-2 font-semibold">Personality</h4>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {draftData.personality}
                </p>
              </section>
            </>
          )}

          {draftData.background && (
            <>
              <Separator />
              <section>
                <h4 className="mb-2 font-semibold">Background</h4>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {draftData.background}
                </p>
              </section>
            </>
          )}
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-4">
        <Button
          size="lg"
          disabled={!canSubmit || submitDraft.isPending}
          onClick={() => submitDraft.mutate(draft.id)}
        >
          {submitDraft.isPending ? (
            'Submitting...'
          ) : (
            <>
              <Send className="mr-2 h-4 w-4" />
              Submit for Review
            </>
          )}
        </Button>

        {isStaff && (
          <Button
            size="lg"
            variant="secondary"
            disabled={!canSubmit || addToRoster.isPending}
            onClick={() => addToRoster.mutate(draft.id)}
          >
            {addToRoster.isPending ? (
              'Adding...'
            ) : (
              <>
                <UserPlus className="mr-2 h-4 w-4" />
                Add to Roster
              </>
            )}
          </Button>
        )}
      </div>

      {(submitDraft.isError || addToRoster.isError) && (
        <p className="text-sm text-destructive">An error occurred. Please try again.</p>
      )}
    </motion.div>
  );
}

interface InfoRowProps {
  label: string;
  value: string | undefined;
}

function InfoRow({ label, value }: InfoRowProps) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn(!value && 'italic text-muted-foreground')}>{value ?? 'Not set'}</span>
    </div>
  );
}
