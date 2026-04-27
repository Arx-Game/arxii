/**
 * Browseable history of narrative messages for the puppeted character.
 * Shown as a section on the character sheet page.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { useMyMessages } from '../queries';
import { MessageRow, MessageRowSkeleton } from './MessageRow';
import type { NarrativeCategory } from '../types';

type FilterTab = 'all' | 'unread' | NarrativeCategory;

const FILTER_TABS: { value: FilterTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'unread', label: 'Unread' },
  { value: 'story', label: 'Story' },
  { value: 'atmosphere', label: 'Atmosphere' },
  { value: 'visions', label: 'Visions' },
  { value: 'happenstance', label: 'Happenstance' },
  { value: 'system', label: 'System' },
];

function isNarrativeCategory(value: FilterTab): value is NarrativeCategory {
  return value !== 'all' && value !== 'unread';
}

export function MessagesSection() {
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all');
  const [page, setPage] = useState(1);

  const queryParams = {
    ...(isNarrativeCategory(activeFilter) ? { category: activeFilter } : {}),
    ...(activeFilter === 'unread' ? { acknowledged: false as const } : {}),
    page,
  };

  const { data, isLoading } = useMyMessages(queryParams);

  const handleFilterChange = (value: string) => {
    setActiveFilter(value as FilterTab);
    setPage(1);
  };

  const results = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasMore = data?.next !== null && data?.next !== undefined;

  return (
    <section aria-labelledby="messages-section-heading">
      <h3 id="messages-section-heading" className="mb-4 text-xl font-semibold">
        Messages
      </h3>

      <Tabs value={activeFilter} onValueChange={handleFilterChange} className="w-full">
        <TabsList className="mb-4 flex h-auto flex-wrap gap-1">
          {FILTER_TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} className="text-xs">
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {FILTER_TABS.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <MessageRowSkeleton key={i} />
                ))}
              </div>
            ) : results.length === 0 ? (
              <p className="py-8 text-center text-muted-foreground">
                No messages yet. Narrative messages from your GM will appear here.
              </p>
            ) : (
              <div className="space-y-2">
                {results.map((delivery) => (
                  <MessageRow key={delivery.id} delivery={delivery} />
                ))}
                {hasMore && (
                  <div className="mt-4 flex justify-center">
                    <Button variant="outline" onClick={() => setPage((p) => p + 1)}>
                      Load more ({totalCount - results.length} remaining)
                    </Button>
                  </div>
                )}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}
