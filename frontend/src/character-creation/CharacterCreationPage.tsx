/**
 * Character Creation Page
 *
 * Main page component for the staged character creation flow.
 */

import { useRealmTheme } from '@/components/realm-theme-provider';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAccount } from '@/store/hooks';
import { pageBackgroundStyle, usePageBackgrounds } from '@/hooks/usePageBackgrounds';
import { AlertCircle } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AppearanceStage,
  AttributesStage,
  DistinctionsStage,
  FinalTouchesStage,
  GiftStage,
  HeritageStage,
  IdentityStage,
  LineageStage,
  OriginStage,
  PathStage,
  ReviewStage,
  StageErrorBoundary,
} from './components';
import { CHAPTERS, ContentsRail, NightPlate, PageTurn } from './folio';
import {
  useCanCreateCharacter,
  useCGExplanations,
  useCreateDraft,
  useDeleteDraft,
  useDraft,
  useUpdateDraft,
} from './queries';
import { Stage, STAGE_LABELS } from './types';
import { getRealmTheme } from './utils';
import './cg.css';

export function CharacterCreationPage() {
  const account = useAccount();
  const { data: canCreate, isLoading: canCreateLoading } = useCanCreateCharacter();
  const { data: draft, isLoading: draftLoading } = useDraft();
  const { data: copy } = useCGExplanations();
  const { data: backgrounds } = usePageBackgrounds();
  const createDraft = useCreateDraft();
  const updateDraft = useUpdateDraft();
  const deleteDraft = useDeleteDraft();
  const { setRealmTheme } = useRealmTheme();
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);

  // Set realm theme from draft area, clear on unmount
  const selectedArea = draft?.selected_area;
  useEffect(() => {
    if (selectedArea) {
      setRealmTheme(getRealmTheme(selectedArea));
    }
    return () => {
      setRealmTheme(null);
    };
  }, [selectedArea, setRealmTheme]);

  // Track beforeLeave callbacks from stages
  const beforeLeaveRef = useRef<(() => Promise<boolean>) | null>(null);

  const isStaff = account?.is_staff ?? false;
  const isLoading = canCreateLoading || draftLoading;

  // Handle stage navigation with beforeLeave check
  const handleStageSelect = useCallback(
    async (stage: Stage) => {
      if (!draft) return;

      // Check if current stage has unsaved changes
      // Store callback in local variable to avoid race condition if ref changes during async call
      const beforeLeave = beforeLeaveRef.current;
      if (beforeLeave) {
        const canLeave = await beforeLeave();
        if (!canLeave) {
          return;
        }
      }

      updateDraft.mutate({ draftId: draft.id, data: { current_stage: stage } });
    },
    [draft, updateDraft]
  );

  // Register/unregister beforeLeave callback
  const registerBeforeLeave = useCallback((check: () => Promise<boolean>) => {
    beforeLeaveRef.current = check;
    return () => {
      beforeLeaveRef.current = null;
    };
  }, []);

  // Restart CG: delete current draft and create a fresh one
  const handleRestart = useCallback(() => {
    if (!draft) return;
    deleteDraft.mutate(draft.id, {
      onSuccess: () => {
        createDraft.mutate();
        setRestartDialogOpen(false);
      },
    });
  }, [draft, deleteDraft, createDraft]);

  // Auto-create draft if user can create and doesn't have one
  useEffect(() => {
    if (!isLoading && canCreate?.can_create && !draft && !createDraft.isPending) {
      // Don't auto-create, let user click the button
    }
  }, [isLoading, canCreate, draft, createDraft.isPending]);

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      </div>
    );
  }

  // Check if user can create characters
  if (!canCreate?.can_create && !draft) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-destructive" />
            <div>
              <h2 className="font-semibold">Cannot Create Character</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {canCreate?.reason || 'You are not eligible to create a new character.'}
              </p>
              <Button asChild className="mt-4" variant="outline">
                <Link to="/">Return Home</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // No draft yet: the arrival plate, the first of the two night moments.
  if (!draft) {
    const backgroundUrl = backgrounds
      ? pageBackgroundStyle(backgrounds, 'cg_stage', 'Character Creation')
          ?.backgroundImage?.toString()
          .replace(/^url\((.*)\)$/, '$1')
      : undefined;
    return (
      <div className="interview">
        <NightPlate
          titleId="arrival-title"
          eyebrow={copy?.arrival_eyebrow ?? 'The Durance · Chapter the First'}
          title={copy?.arrival_title ?? 'One stands before us'}
          backgroundImage={backgroundUrl}
          door={{
            label: createDraft.isPending
              ? 'Opening the record...'
              : (copy?.arrival_door ?? 'Open the record'),
            onClick: () => createDraft.mutate(),
            disabled: createDraft.isPending,
          }}
          quiet={{ label: copy?.arrival_quiet ?? 'or return to the Hall', to: '/' }}
        >
          {copy?.origin_lore_intro && <p className="plate-sub">{copy.origin_lore_intro}</p>}
        </NightPlate>
      </div>
    );
  }

  // Render current stage
  const renderStage = () => {
    switch (draft.current_stage) {
      case Stage.ORIGIN:
        return <OriginStage draft={draft} />;
      case Stage.HERITAGE:
        return <HeritageStage draft={draft} onStageSelect={handleStageSelect} />;
      case Stage.LINEAGE:
        return <LineageStage draft={draft} onStageSelect={handleStageSelect} />;
      case Stage.ATTRIBUTES:
        return <AttributesStage draft={draft} />;
      case Stage.PATH:
        return <PathStage draft={draft} />;
      case Stage.DISTINCTIONS:
        return <DistinctionsStage draft={draft} onRegisterBeforeLeave={registerBeforeLeave} />;
      case Stage.GIFT:
        return <GiftStage draft={draft} onRegisterBeforeLeave={registerBeforeLeave} />;
      case Stage.APPEARANCE:
        return (
          <AppearanceStage
            draft={draft}
            isStaff={isStaff}
            onRegisterBeforeLeave={registerBeforeLeave}
          />
        );
      case Stage.IDENTITY:
        return <IdentityStage draft={draft} onRegisterBeforeLeave={registerBeforeLeave} />;
      case Stage.FINAL_TOUCHES:
        return <FinalTouchesStage draft={draft} onRegisterBeforeLeave={registerBeforeLeave} />;
      case Stage.REVIEW:
        return <ReviewStage draft={draft} isStaff={isStaff} onStageSelect={handleStageSelect} />;
      default:
        return <OriginStage draft={draft} />;
    }
  };

  const currentIndex = CHAPTERS.findIndex((c) => c.stage === draft.current_stage);
  const prev = CHAPTERS[currentIndex - 1]?.stage;
  const nextStage = CHAPTERS[currentIndex + 1]?.stage;

  const restartDoor = (
    <button type="button" onClick={() => setRestartDialogOpen(true)}>
      {/* PLACEHOLDER: Apostate rewrite */}
      Tear out these pages and begin again
    </button>
  );

  return (
    <div className="interview">
      <div className="interview-grid">
        <ContentsRail
          currentStage={draft.current_stage}
          stageCompletion={draft.stage_completion}
          stageErrors={draft.stage_errors ?? {}}
          onStageSelect={handleStageSelect}
          restartSlot={restartDoor}
        />
        <div className="chapter-column" id={`chapter-${draft.current_stage}`}>
          <StageErrorBoundary
            currentStage={draft.current_stage}
            onNavigateToStage={handleStageSelect}
          >
            {renderStage()}
          </StageErrorBoundary>
          {/* Stages that own their own PageTurn (Origin, Review) render nothing here. */}
          {draft.current_stage !== Stage.ORIGIN && draft.current_stage !== Stage.REVIEW && (
            <PageTurn
              back={
                prev !== undefined
                  ? { label: `Back: ${STAGE_LABELS[prev]}`, onClick: () => handleStageSelect(prev) }
                  : undefined
              }
              next={
                nextStage !== undefined
                  ? {
                      label: `Turn the page: ${STAGE_LABELS[nextStage]}`,
                      onClick: () => handleStageSelect(nextStage),
                    }
                  : undefined
              }
            />
          )}
        </div>
      </div>

      <Dialog open={restartDialogOpen} onOpenChange={setRestartDialogOpen}>
        <DialogContent className="rounded-none">
          <DialogHeader>
            {/* PLACEHOLDER: Apostate rewrite */}
            <DialogTitle className="theme-heading">Tear out these pages</DialogTitle>
            <DialogDescription>
              {/* PLACEHOLDER: Apostate rewrite */}
              Every chapter written so far is lost, and the record begins again at Origin.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              className="rounded-none"
              onClick={() => setRestartDialogOpen(false)}
            >
              Keep what is written
            </Button>
            <Button
              variant="destructive"
              className="rounded-none"
              onClick={handleRestart}
              disabled={deleteDraft.isPending || createDraft.isPending}
            >
              {deleteDraft.isPending || createDraft.isPending ? 'Tearing out...' : 'Tear them out'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
