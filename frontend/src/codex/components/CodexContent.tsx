import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { WelcomeSplash } from './WelcomeSplash';
import { MasonryGrid } from './MasonryGrid';
import { CategoryCard } from './CategoryCard';
import { SubjectCard } from './SubjectCard';
import { EntryGrid } from './EntryGrid';
import { EntryDetail } from './EntryDetail';
import {
  useCodexTree,
  useCodexSubject,
  useCodexSubjectChildren,
  useCodexEntries,
  useCodexEntry,
} from '../queries';

interface CodexContentProps {
  categoryId?: number;
  subjectId?: number;
  entryId?: number;
  onSelectCategory: (categoryId: number) => void;
  onSelectSubject: (subjectId: number) => void;
  onSelectEntry: (entryId: number) => void;
  onNavigateBreadcrumb: (type: 'home' | 'category' | 'subject', id?: number) => void;
}

export function CodexContent({
  categoryId,
  subjectId,
  entryId,
  onSelectCategory,
  onSelectSubject,
  onSelectEntry,
  onNavigateBreadcrumb,
}: CodexContentProps) {
  // Entry detail view
  if (entryId) {
    return <EntryDetailView entryId={entryId} onNavigateBreadcrumb={onNavigateBreadcrumb} />;
  }

  // Subject view (children or entries)
  if (subjectId) {
    return (
      <SubjectView
        subjectId={subjectId}
        onSelectSubject={onSelectSubject}
        onSelectEntry={onSelectEntry}
      />
    );
  }

  // Category view (subjects)
  if (categoryId) {
    return <CategoryView categoryId={categoryId} onSelectSubject={onSelectSubject} />;
  }

  // Home view (all categories or welcome)
  return <HomeView onSelectCategory={onSelectCategory} />;
}

function LoadingSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-8 w-1/2" />
      </CardHeader>
      <CardContent>
        <Skeleton className="mb-2 h-4 w-full" />
        <Skeleton className="mb-2 h-4 w-3/4" />
        <Skeleton className="h-4 w-5/6" />
      </CardContent>
    </Card>
  );
}

function HomeView({ onSelectCategory }: { onSelectCategory: (id: number) => void }) {
  const { data: tree, isLoading } = useCodexTree();

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (!tree || tree.length === 0) {
    return <WelcomeSplash />;
  }

  // Show welcome if no categories have content
  const hasContent = tree.some((cat) => cat.subjects.length > 0);
  if (!hasContent) {
    return <WelcomeSplash />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Browse Categories</h2>
      <MasonryGrid>
        {tree.map((category) => (
          <CategoryCard
            key={category.id}
            name={category.name}
            description={category.description}
            onClick={() => onSelectCategory(category.id)}
          />
        ))}
      </MasonryGrid>
    </div>
  );
}

function CategoryView({
  categoryId,
  onSelectSubject,
}: {
  categoryId: number;
  onSelectSubject: (id: number) => void;
}) {
  // Use tree data which includes subjects (already cached from sidebar)
  const { data: tree, isLoading } = useCodexTree();

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  // Find category in tree
  const category = tree?.find((cat) => cat.id === categoryId);

  if (!category) {
    return <div className="text-muted-foreground">Category not found</div>;
  }

  if (category.subjects.length === 0) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-semibold">{category.name}</h2>
        <p className="text-muted-foreground">{category.description}</p>
        <p className="text-sm text-muted-foreground">No subjects available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">{category.name}</h2>
        {category.description && (
          <p className="mt-1 text-muted-foreground">{category.description}</p>
        )}
      </div>
      <MasonryGrid>
        {category.subjects.map((subject) => (
          <SubjectCard
            key={subject.id}
            name={subject.name}
            hasChildren={subject.has_children}
            onClick={() => onSelectSubject(subject.id)}
          />
        ))}
      </MasonryGrid>
    </div>
  );
}

function SubjectView({
  subjectId,
  onSelectSubject,
  onSelectEntry,
}: {
  subjectId: number;
  onSelectSubject: (id: number) => void;
  onSelectEntry: (id: number) => void;
}) {
  const { data: subject, isLoading: subjectLoading } = useCodexSubject(subjectId);
  const { data: children, isLoading: childrenLoading } = useCodexSubjectChildren(subjectId);
  const { data: entries, isLoading: entriesLoading } = useCodexEntries(subjectId);

  const isLoading = subjectLoading || childrenLoading || entriesLoading;

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (!subject) {
    return <div className="text-muted-foreground">Subject not found</div>;
  }

  const hasChildren = children && children.length > 0;

  // If has children, show child subjects
  if (hasChildren) {
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-xl font-semibold">{subject.name}</h2>
          {subject.description && (
            <p className="mt-1 text-muted-foreground">{subject.description}</p>
          )}
        </div>
        <MasonryGrid>
          {children.map((child) => (
            <SubjectCard
              key={child.id}
              name={child.name}
              hasChildren={child.has_children}
              onClick={() => onSelectSubject(child.id)}
            />
          ))}
        </MasonryGrid>
      </div>
    );
  }

  // Leaf node - show entries
  if (!entries || entries.length === 0) {
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-xl font-semibold">{subject.name}</h2>
          {subject.description && (
            <p className="mt-1 text-muted-foreground">{subject.description}</p>
          )}
        </div>
        <p className="text-sm text-muted-foreground">No entries available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">{subject.name}</h2>
        {subject.description && <p className="mt-1 text-muted-foreground">{subject.description}</p>}
      </div>
      <EntryGrid entries={entries} onSelectEntry={onSelectEntry} />
    </div>
  );
}

function EntryDetailView({
  entryId,
  onNavigateBreadcrumb,
}: {
  entryId: number;
  onNavigateBreadcrumb: (type: 'home' | 'category' | 'subject', id?: number) => void;
}) {
  const { data: entry, isLoading } = useCodexEntry(entryId);

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (!entry) {
    return <div className="text-muted-foreground">Entry not found</div>;
  }

  return <EntryDetail entry={entry} onNavigateBreadcrumb={onNavigateBreadcrumb} />;
}
