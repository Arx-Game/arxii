import { Link } from 'react-router-dom';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export function LoreTabs() {
  return (
    <section className="container mx-auto py-12">
      <Tabs defaultValue="setting" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="setting">Setting</TabsTrigger>
          <TabsTrigger value="factions">Houses/Factions</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>
        <TabsContent value="setting">
          <Accordion type="single" collapsible>
            <AccordionItem value="setting-item">
              <AccordionTrigger>World Overview</AccordionTrigger>
              <AccordionContent>
                <p className="mb-2">
                  Discover the basics of Arx II's setting and its central themes.
                </p>
                <Link className="text-primary underline" to="/lore/setting">
                  Read more
                </Link>
                .
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </TabsContent>
        <TabsContent value="factions">
          <Accordion type="single" collapsible>
            <AccordionItem value="factions-item">
              <AccordionTrigger>Key Players</AccordionTrigger>
              <AccordionContent>
                <p className="mb-2">Meet the houses and factions competing for influence.</p>
                <Link className="text-primary underline" to="/lore/houses">
                  Read more
                </Link>
                .
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </TabsContent>
        <TabsContent value="timeline">
          <Accordion type="single" collapsible>
            <AccordionItem value="timeline-item">
              <AccordionTrigger>Historical Events</AccordionTrigger>
              <AccordionContent>
                <p className="mb-2">Explore the major events that shaped the realm.</p>
                <Link className="text-primary underline" to="/lore/timeline">
                  Read more
                </Link>
                .
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </TabsContent>
      </Tabs>
    </section>
  );
}
