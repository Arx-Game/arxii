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
  DialogTrigger,
} from '@/components/ui/dialog';
import { useAccount } from '@/store/hooks';
import { AnimatePresence } from 'framer-motion';
import { AlertCircle, Plus, RotateCcw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AppearanceStage,
  AttributesStage,
  DistinctionsStage,
  FinalTouchesStage,
  HeritageStage,
  IdentityStage,
  LineageStage,
  MagicStage,
  OriginStage,
  PathSkillsStage,
  ReviewStage,
  StageErrorBoundary,
  StageStepper,
} from './components';
import {
  useCanCreateCharacter,
  useCreateDraft,
  useDeleteDraft,
  useDraft,
  useUpdateDraft,
} from './queries';
import { Stage } from './types';
import { getRealmTheme } from './utils';

export function CharacterCreationPage() {
  const account = useAccount();
  const { data: canCreate, isLoading: canCreateLoading } = useCanCreateCharacter();
  const { data: draft, isLoading: draftLoading } = useDraft();
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

  // No draft yet - show start button
  if (!draft) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <div className="py-12 text-center">
          <h1 className="text-3xl font-bold">Create a New Character</h1>
          <p className="mx-auto mt-4 max-w-lg text-muted-foreground">
            Begin your journey by creating a character. You'll define their origin, heritage,
            abilities, and story through a guided process.
          </p>
          <Button
            size="lg"
            className="mt-8"
            onClick={() => createDraft.mutate()}
            disabled={createDraft.isPending}
          >
            {createDraft.isPending ? (
              'Creating...'
            ) : (
              <>
                <Plus className="mr-2 h-5 w-5" />
                Start Character Creation
              </>
            )}
          </Button>
        </div>
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
      case Stage.PATH_SKILLS:
        return <PathSkillsStage draft={draft} />;
      case Stage.DISTINCTIONS:
        return <DistinctionsStage draft={draft} onRegisterBeforeLeave={registerBeforeLeave} />;
      case Stage.MAGIC:
        return <MagicStage draft={draft} onRegisterBeforeLeave={registerBeforeLeave} />;
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

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="theme-heading text-3xl font-bold">Character Creation</h1>
      </header>

      <div className="mb-8 flex items-start gap-4">
        <div className="flex-1">
          <StageStepper
            currentStage={draft.current_stage}
            stageCompletion={draft.stage_completion}
            onStageSelect={handleStageSelect}
          />
        </div>
        <Dialog open={restartDialogOpen} onOpenChange={setRestartDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="shrink-0 text-muted-foreground">
              <RotateCcw className="mr-1.5 h-4 w-4" />
              <span className="hidden sm:inline">Restart</span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Restart Character Creation?</DialogTitle>
              <DialogDescription>
                This will permanently delete all your current progress — selections, stats, magic,
                appearance, everything — and start a completely fresh character. This cannot be
                undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRestartDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleRestart}
                disabled={deleteDraft.isPending || createDraft.isPending}
              >
                {deleteDraft.isPending || createDraft.isPending
                  ? 'Restarting...'
                  : 'Delete & Restart'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <main className="min-h-[400px]">
        <StageErrorBoundary
          currentStage={draft.current_stage}
          onNavigateToStage={handleStageSelect}
        >
          <AnimatePresence mode="wait">{renderStage()}</AnimatePresence>
        </StageErrorBoundary>
      </main>

      {/* Navigation buttons */}
      <footer className="mt-12 flex justify-between border-t pt-6">
        <Button
          variant="outline"
          disabled={draft.current_stage === Stage.ORIGIN}
          onClick={() => handleStageSelect((draft.current_stage - 1) as Stage)}
        >
          Previous
        </Button>
        <Button
          disabled={draft.current_stage === Stage.REVIEW}
          onClick={() => handleStageSelect((draft.current_stage + 1) as Stage)}
        >
          Next
        </Button>
      </footer>
    </div>
  );
}
