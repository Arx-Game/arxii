/**
 * StoryAuthorTree — sidebar/inline tree showing chapters → episodes → beats + transitions.
 *
 * Renders for the selected story in StoryAuthorPage. Provides inline
 * Edit/Delete/Add buttons for chapters, episodes, beats, and transitions.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { ChevronDown, ChevronRight, Plus, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  useChapterList,
  useEpisodeList,
  useBeatList,
  useTransitionList,
  useDeleteChapter,
  useDeleteEpisode,
  useDeleteBeat,
  useDeleteTransition,
} from '../queries';
import type { ChapterList, EpisodeList, Beat, Transition, Story } from '../types';
import { ChapterFormDialog } from './ChapterFormDialog';
import { EpisodeFormDialog } from './EpisodeFormDialog';
import { BeatFormDialog } from './BeatFormDialog';
import { TransitionFormDialog } from './TransitionFormDialog';

// ---------------------------------------------------------------------------
// Delete confirm helper
// ---------------------------------------------------------------------------

interface DeleteButtonProps {
  label: string;
  onConfirm: () => void;
  disabled?: boolean;
}

function DeleteButton({ label, onConfirm, disabled }: DeleteButtonProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
          disabled={disabled}
          aria-label={`Delete ${label}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {label}?</AlertDialogTitle>
          <AlertDialogDescription>
            This action cannot be undone. All nested content will be permanently deleted.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------
// Transition row
// ---------------------------------------------------------------------------

interface TransitionRowProps {
  transition: Transition;
  sourceEpisodeId: number;
  storyId: number;
}

function TransitionRow({ transition, sourceEpisodeId, storyId }: TransitionRowProps) {
  const [editOpen, setEditOpen] = useState(false);
  const deleteMutation = useDeleteTransition();

  function handleDelete() {
    deleteMutation.mutate(transition.id, {
      onSuccess: () => toast.success('Transition deleted'),
      onError: () => toast.error('Failed to delete transition'),
    });
  }

  const targetLabel = transition.target_episode_title ?? '(frontier)';

  return (
    <li
      className="flex items-center justify-between py-1 pl-6 text-xs"
      data-testid="transition-row"
    >
      <span className="text-muted-foreground">
        → <span className="font-medium text-foreground">{targetLabel}</span>{' '}
        <span className="text-muted-foreground">({transition.mode})</span>
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={() => setEditOpen(true)}
          aria-label="Edit transition"
        >
          <Pencil className="h-3 w-3" />
        </Button>
        <DeleteButton
          label="Transition"
          onConfirm={handleDelete}
          disabled={deleteMutation.isPending}
        />
      </div>
      <TransitionFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        sourceEpisodeId={sourceEpisodeId}
        storyId={storyId}
        transition={transition}
      />
    </li>
  );
}

// ---------------------------------------------------------------------------
// Beat row
// ---------------------------------------------------------------------------

interface BeatRowAuthorProps {
  beat: Beat;
}

function BeatRowAuthor({ beat }: BeatRowAuthorProps) {
  const [editOpen, setEditOpen] = useState(false);
  const deleteMutation = useDeleteBeat();

  function handleDelete() {
    deleteMutation.mutate(beat.id, {
      onSuccess: () => toast.success('Beat deleted'),
      onError: () => toast.error('Failed to delete beat'),
    });
  }

  return (
    <li
      className="flex items-center justify-between py-1 pl-8 text-xs"
      data-testid="beat-row-author"
    >
      <span>
        <span className="font-mono text-muted-foreground">#{beat.id}</span>{' '}
        <span className="inline-block max-w-[200px] truncate align-bottom">
          {beat.internal_description?.slice(0, 60) ?? '(no description)'}
        </span>
        <span className="ml-1 text-muted-foreground">({beat.predicate_type})</span>
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={() => setEditOpen(true)}
          aria-label="Edit beat"
        >
          <Pencil className="h-3 w-3" />
        </Button>
        <DeleteButton label="Beat" onConfirm={handleDelete} disabled={deleteMutation.isPending} />
      </div>
      <BeatFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        episodeId={beat.episode}
        beat={beat}
      />
    </li>
  );
}

// ---------------------------------------------------------------------------
// Episode row (expanded shows beats and transitions)
// ---------------------------------------------------------------------------

interface EpisodeRowProps {
  episode: EpisodeList;
  storyId: number;
}

function EpisodeRowAuthor({ episode, storyId }: EpisodeRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [addBeatOpen, setAddBeatOpen] = useState(false);
  const [addTransitionOpen, setAddTransitionOpen] = useState(false);
  const deleteMutation = useDeleteEpisode();

  const { data: beatsData } = useBeatList(
    expanded ? { episode: episode.id, page_size: 100 } : undefined
  );
  const { data: transitionsData } = useTransitionList(
    expanded ? { source_episode: episode.id, page_size: 100 } : undefined
  );

  const beats = beatsData?.results ?? [];
  const transitions = transitionsData?.results ?? [];

  function handleDelete() {
    deleteMutation.mutate(episode.id, {
      onSuccess: () => toast.success('Episode deleted'),
      onError: () => toast.error('Failed to delete episode'),
    });
  }

  return (
    <li data-testid="episode-row-author">
      <div className="flex items-center justify-between rounded py-1 pl-4 hover:bg-muted/30">
        <button
          type="button"
          className="flex flex-1 items-center gap-1 text-left text-sm"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <span>{episode.title}</span>
          {episode.order !== undefined && (
            <span className="ml-1 text-xs text-muted-foreground">#{episode.order}</span>
          )}
        </button>
        <div className="flex items-center gap-1 pr-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setAddBeatOpen(true)}
            aria-label="Add Beat"
          >
            <Plus className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setEditOpen(true)}
            aria-label="Edit episode"
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <DeleteButton
            label="Episode"
            onConfirm={handleDelete}
            disabled={deleteMutation.isPending}
          />
        </div>
      </div>

      {expanded && (
        <ul className="pl-2">
          {beats.length === 0 && transitions.length === 0 ? (
            <li className="py-1 pl-8 text-xs italic text-muted-foreground">
              No beats or transitions.
            </li>
          ) : (
            <>
              {beats.map((beat) => (
                <BeatRowAuthor key={beat.id} beat={beat} />
              ))}
              {transitions.map((t) => (
                <TransitionRow
                  key={t.id}
                  transition={t}
                  sourceEpisodeId={episode.id}
                  storyId={storyId}
                />
              ))}
            </>
          )}
          <li className="py-1 pl-6">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 gap-1 text-xs text-muted-foreground"
              onClick={() => setAddTransitionOpen(true)}
            >
              <Plus className="h-3 w-3" /> Add Transition
            </Button>
          </li>
        </ul>
      )}

      <EpisodeFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        chapterId={episode.chapter as unknown as number}
        episode={episode}
      />
      <BeatFormDialog open={addBeatOpen} onOpenChange={setAddBeatOpen} episodeId={episode.id} />
      <TransitionFormDialog
        open={addTransitionOpen}
        onOpenChange={setAddTransitionOpen}
        sourceEpisodeId={episode.id}
        storyId={storyId}
      />
    </li>
  );
}

// ---------------------------------------------------------------------------
// Chapter row (expanded shows episodes)
// ---------------------------------------------------------------------------

interface ChapterRowProps {
  chapter: ChapterList;
  storyId: number;
}

function ChapterRow({ chapter, storyId }: ChapterRowProps) {
  const [expanded, setExpanded] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [addEpisodeOpen, setAddEpisodeOpen] = useState(false);
  const deleteMutation = useDeleteChapter();

  const { data: episodesData } = useEpisodeList({ chapter: chapter.id, page_size: 100 });
  const episodes = episodesData?.results ?? [];

  function handleDelete() {
    deleteMutation.mutate(chapter.id, {
      onSuccess: () => toast.success('Chapter deleted'),
      onError: () => toast.error('Failed to delete chapter'),
    });
  }

  return (
    <li data-testid="chapter-row">
      <div className="flex items-center justify-between rounded py-1.5 hover:bg-muted/30">
        <button
          type="button"
          className="flex flex-1 items-center gap-1 text-left text-sm font-medium"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <span>{chapter.title}</span>
        </button>
        <div className="flex items-center gap-1 pr-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setAddEpisodeOpen(true)}
            aria-label="Add Episode"
          >
            <Plus className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setEditOpen(true)}
            aria-label="Edit chapter"
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <DeleteButton
            label="Chapter"
            onConfirm={handleDelete}
            disabled={deleteMutation.isPending}
          />
        </div>
      </div>

      {expanded && (
        <ul className="pl-2">
          {episodes.length === 0 ? (
            <li className="py-1 pl-4 text-xs italic text-muted-foreground">No episodes yet.</li>
          ) : (
            episodes.map((ep) => <EpisodeRowAuthor key={ep.id} episode={ep} storyId={storyId} />)
          )}
        </ul>
      )}

      <ChapterFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        storyId={storyId}
        chapter={chapter}
      />
      <EpisodeFormDialog
        open={addEpisodeOpen}
        onOpenChange={setAddEpisodeOpen}
        chapterId={chapter.id}
      />
    </li>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface StoryAuthorTreeProps {
  story: Story;
}

// ---------------------------------------------------------------------------
// Main tree
// ---------------------------------------------------------------------------

export function StoryAuthorTree({ story }: StoryAuthorTreeProps) {
  const [addChapterOpen, setAddChapterOpen] = useState(false);
  const { data: chaptersData } = useChapterList({ story: story.id, page_size: 100 });
  const chapters = chaptersData?.results ?? [];

  return (
    <div data-testid="story-author-tree">
      {chapters.length === 0 ? (
        <p className="py-2 text-sm italic text-muted-foreground">No chapters yet.</p>
      ) : (
        <ul className="space-y-0.5">
          {chapters.map((ch) => (
            <ChapterRow key={ch.id} chapter={ch} storyId={story.id} />
          ))}
        </ul>
      )}

      <div className="mt-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-1"
          onClick={() => setAddChapterOpen(true)}
          data-testid="add-chapter-btn"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Chapter
        </Button>
      </div>

      <ChapterFormDialog
        open={addChapterOpen}
        onOpenChange={setAddChapterOpen}
        storyId={story.id}
      />
    </div>
  );
}
