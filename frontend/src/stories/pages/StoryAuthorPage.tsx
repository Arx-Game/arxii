/**
 * StoryAuthorPage — story author CRUD editor.
 *
 * Two-pane layout:
 *   Left:  sidebar listing user's stories (or all if staff)
 *   Right: selected story header + chapter/episode/beat tree
 *
 * Permission gating: the endpoint 403s for non-Lead-GM. Same throwOnError:false
 * pattern as GMQueuePage and StaffWorkloadPage.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
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
import { listStories, getStory } from '../api';
import { storiesKeys, useDeleteStory } from '../queries';
import type { Story, StoryList } from '../types';
import { ScopeBadge } from '../components/ScopeBadge';
import { StoryFormDialog } from '../components/StoryFormDialog';
import { StoryAuthorTree } from '../components/StoryAuthorTree';

// ---------------------------------------------------------------------------
// Access denied fallback
// ---------------------------------------------------------------------------

function AccessDeniedPage() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center text-center">
      <h2 className="text-xl font-semibold">Access Denied</h2>
      <p className="mt-2 max-w-md text-muted-foreground">
        This page is only accessible to Lead GMs and staff. Contact an administrator if you should
        have access.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="flex gap-6" data-testid="author-loading">
      <div className="w-56 space-y-2">
        <Skeleton className="h-8 w-full" />
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
      <div className="flex-1 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Story sidebar item
// ---------------------------------------------------------------------------

interface StoryListItemProps {
  story: StoryList;
  selected: boolean;
  onSelect: () => void;
}

function StoryListItem({ story, selected, onSelect }: StoryListItemProps) {
  return (
    <button
      type="button"
      className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
        selected ? 'bg-accent font-medium' : ''
      }`}
      onClick={onSelect}
      data-testid="story-sidebar-item"
    >
      <span className="block truncate">{story.title}</span>
      <ScopeBadge scope={story.scope ?? 'character'} className="mt-0.5 text-xs" />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Selected story main pane
// ---------------------------------------------------------------------------

interface StoryMainPaneProps {
  story: Story;
  onEdited: () => void;
  onDeleted: () => void;
}

function StoryMainPane({ story, onEdited, onDeleted }: StoryMainPaneProps) {
  const [editOpen, setEditOpen] = useState(false);
  const deleteMutation = useDeleteStory();

  function handleDelete() {
    deleteMutation.mutate(story.id, {
      onSuccess: () => {
        toast.success('Story deleted');
        onDeleted();
      },
      onError: () => toast.error('Failed to delete story'),
    });
  }

  return (
    <div className="min-w-0 flex-1" data-testid="story-main-pane">
      {/* Story header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold">{story.title}</h2>
            <ScopeBadge scope={story.scope ?? 'character'} />
          </div>
          {story.description && (
            <p className="mt-1 text-sm text-muted-foreground">{story.description}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() => setEditOpen(true)}
            data-testid="edit-story-btn"
          >
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-1 text-destructive hover:text-destructive"
                data-testid="delete-story-btn"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete Story?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently delete &quot;{story.title}&quot; and all its chapters,
                  episodes, and beats. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDelete}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Delete Story'}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* Chapter/episode/beat tree */}
      <StoryAuthorTree story={story} />

      <StoryFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        story={story}
        onSuccess={onEdited}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function StoryAuthorPage() {
  const [selectedStoryId, setSelectedStoryId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [storyVersion, setStoryVersion] = useState(0);

  // Load story list — let API permission gating surface naturally.
  // Use throwOnError: false so we can render the 403 page ourselves.
  const { data, isLoading, error } = useQuery({
    queryKey: [...storiesKeys.storyList(), 'author'] as const,
    queryFn: () => listStories({ page_size: 100 }),
    throwOnError: false,
    retry: false,
  });

  // Load selected story detail to get the full Story type for the main pane.
  const { data: selectedStory, refetch: refetchSelected } = useQuery({
    queryKey: [...storiesKeys.story(selectedStoryId ?? 0), storyVersion] as const,
    queryFn: () => getStory(selectedStoryId!),
    enabled: selectedStoryId !== null,
    throwOnError: false,
  });

  let content: React.ReactNode;

  if (error) {
    const status = (error as Error & { status?: number }).status;
    if (status === 403) {
      content = <AccessDeniedPage />;
    } else {
      throw error;
    }
  } else if (isLoading) {
    content = <LoadingSkeleton />;
  } else if (data) {
    const stories = data.results;

    content = (
      <div className="flex gap-6">
        {/* Sidebar */}
        <aside className="w-56 shrink-0" data-testid="stories-sidebar">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">My Stories</p>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setCreateOpen(true)}
              aria-label="New Story"
              data-testid="new-story-btn"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          {stories.length === 0 ? (
            <p className="text-sm italic text-muted-foreground" data-testid="stories-sidebar-empty">
              No stories yet. Create one to get started.
            </p>
          ) : (
            <ul className="space-y-0.5" data-testid="stories-sidebar-list">
              {stories.map((story) => (
                <li key={story.id}>
                  <StoryListItem
                    story={story}
                    selected={selectedStoryId === story.id}
                    onSelect={() => setSelectedStoryId(story.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Main pane */}
        <main className="min-w-0 flex-1">
          {selectedStory ? (
            <StoryMainPane
              story={selectedStory}
              onEdited={() => {
                setStoryVersion((v) => v + 1);
                void refetchSelected();
              }}
              onDeleted={() => {
                setSelectedStoryId(null);
              }}
            />
          ) : (
            <div
              className="flex min-h-48 items-center justify-center text-sm text-muted-foreground"
              data-testid="no-story-selected"
            >
              Select a story from the sidebar or create a new one.
            </div>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-8 text-2xl font-bold">Story Author</h1>
      {content}

      <StoryFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccess={(story) => {
          setSelectedStoryId(story.id);
        }}
      />
    </div>
  );
}
