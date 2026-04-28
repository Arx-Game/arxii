/**
 * TableBulletin — the full bulletin board section in TableDetailPage.
 *
 * Layout:
 *   Section selector (Table-Wide + one per story the viewer participates in)
 *   List of BulletinPostCards for the selected section
 *   "New Post" button (GM/staff only) → CreateBulletinPostDialog
 *
 * The section selector shows:
 *   - "Table-Wide" always
 *   - One entry per story at this table (backend already permission-scopes
 *     the story list to stories the viewer participates in)
 *
 * Posts are fetched by passing `table=<id>` plus `story=<id>` (or no story
 * param for table-wide). The backend queryset filters by read access.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useStoryList } from '@/stories/queries';
import { useBulletinPosts } from '../queries';
import { BulletinPostCard, BulletinPostCardSkeleton } from './BulletinPostCard';
import { CreateBulletinPostDialog } from './CreateBulletinPostDialog';
import type { GMTable } from '../types';
import type { StoryList } from '@/stories/types';

// ---------------------------------------------------------------------------
// Section ID type — null means "table-wide"
// ---------------------------------------------------------------------------

type SectionId = number | null;

// ---------------------------------------------------------------------------
// Section selector button group
// ---------------------------------------------------------------------------

interface SectionSelectorProps {
  current: SectionId;
  stories: StoryList[];
  onChange: (id: SectionId) => void;
}

function SectionSelector({ current, stories, onChange }: SectionSelectorProps) {
  return (
    <div
      role="tablist"
      aria-label="Bulletin sections"
      className="flex flex-wrap gap-1 border-b pb-2"
    >
      <button
        type="button"
        role="tab"
        aria-selected={current === null}
        onClick={() => onChange(null)}
        className={[
          'rounded px-3 py-1 text-sm font-medium transition-colors',
          current === null
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted',
        ].join(' ')}
      >
        Table-Wide
      </button>
      {stories.map((story) => (
        <button
          key={story.id}
          type="button"
          role="tab"
          aria-selected={current === story.id}
          onClick={() => onChange(story.id)}
          className={[
            'rounded px-3 py-1 text-sm font-medium transition-colors',
            current === story.id
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted',
          ].join(' ')}
        >
          {story.title}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section content
// ---------------------------------------------------------------------------

interface SectionContentProps {
  tableId: number;
  storyId: SectionId;
  isGMOrStaff: boolean;
  /** The viewer's persona PK for reply submission. For GMs this is their GM persona. */
  viewerPersonaId?: number;
}

function SectionContent({ tableId, storyId, isGMOrStaff, viewerPersonaId }: SectionContentProps) {
  const params = storyId !== null ? { table: tableId, story: storyId } : { table: tableId };

  const { data, isLoading } = useBulletinPosts(params);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <BulletinPostCardSkeleton />
        <BulletinPostCardSkeleton />
      </div>
    );
  }

  const posts = data?.results ?? [];

  if (posts.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground" data-testid="bulletin-empty">
        No posts in this section yet.
        {isGMOrStaff
          ? ' Use the button below to author the first post.'
          : ' The Lead GM can author the first post.'}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {posts.map((post) => (
        <BulletinPostCard
          key={post.id}
          post={post}
          isGMOrStaff={isGMOrStaff}
          canReply={post.allow_replies}
          viewerPersonaId={viewerPersonaId}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TableBulletin
// ---------------------------------------------------------------------------

interface TableBulletinProps {
  table: GMTable;
}

export function TableBulletin({ table }: TableBulletinProps) {
  const [activeSection, setActiveSection] = useState<SectionId>(null);

  const isGMOrStaff = table.viewer_role === 'gm' || table.viewer_role === 'staff';

  // Fetch stories at this table for the section selector.
  // The backend scopes the list to stories the viewer participates in (for non-GMs).
  const { data: storiesData } = useStoryList({ primary_table: table.id });
  const stories: StoryList[] = storiesData?.results ?? [];

  // When the active section's story is no longer visible (e.g., after a data
  // refresh removes a story), fall back to table-wide.
  const resolvedSection: SectionId =
    activeSection !== null && !stories.some((s) => s.id === activeSection) ? null : activeSection;

  return (
    <div className="space-y-4">
      {/* Section selector */}
      <SectionSelector current={resolvedSection} stories={stories} onChange={setActiveSection} />

      {/* Post list for selected section */}
      <SectionContent
        tableId={table.id}
        storyId={resolvedSection}
        isGMOrStaff={isGMOrStaff}
        viewerPersonaId={undefined}
      />

      {/* New Post button — GM/staff only */}
      {isGMOrStaff && (
        <div className="flex justify-start border-t pt-4">
          <CreateBulletinPostDialog
            tableId={table.id}
            gmPersonaId={0}
            stories={stories}
            initialStoryId={resolvedSection}
          >
            <Button variant="outline" size="sm">
              + New Post
            </Button>
          </CreateBulletinPostDialog>
        </div>
      )}
    </div>
  );
}
