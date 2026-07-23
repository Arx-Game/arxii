import { Link } from 'react-router-dom';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { useFeaturedCodexEntries } from '@/codex/queries';

export function FeaturedLore() {
  const { data: entries, isLoading } = useFeaturedCodexEntries();

  if (isLoading) {
    return (
      <section className="container mx-auto py-12">
        <p className="text-muted-foreground">Loading lore...</p>
      </section>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <section className="container mx-auto py-12 text-center">
        <Link className="text-primary underline" to="/codex">
          Explore the world
        </Link>
      </section>
    );
  }

  return (
    <section className="container mx-auto py-12">
      <Accordion type="single" collapsible>
        {entries.map((entry) => (
          <AccordionItem key={entry.id} value={`entry-${entry.id}`}>
            <AccordionTrigger>{entry.name}</AccordionTrigger>
            <AccordionContent>
              <p className="mb-2 text-muted-foreground">{entry.summary}</p>
              <Link className="text-primary underline" to={`/codex?entry=${entry.id}`}>
                Read more
              </Link>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  );
}
