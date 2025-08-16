import { Link } from 'react-router-dom';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export function NewPlayerSection() {
  return (
    <section className="container mx-auto py-12">
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="how">How to Play</TabsTrigger>
          <TabsTrigger value="roster">Roster Primer</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <Accordion type="single" collapsible>
            <AccordionItem value="overview-item">
              <AccordionTrigger>Welcome</AccordionTrigger>
              <AccordionContent>
                <p className="mb-2">
                  Placeholder overview copy for new players. Learn the basics of the game and
                  explore what awaits.
                </p>
                <p>
                  <Link className="text-primary underline" to="/how-to-start">
                    Learn how to play
                  </Link>{' '}
                  or browse the{' '}
                  <Link className="text-primary underline" to="/roster">
                    character roster
                  </Link>
                  .
                </p>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </TabsContent>
        <TabsContent value="how">
          <Accordion type="single" collapsible>
            <AccordionItem value="how-item">
              <AccordionTrigger>Getting Started</AccordionTrigger>
              <AccordionContent>
                <p className="mb-2">Placeholder instructions on how to dive into the world.</p>
                <Link className="text-primary underline" to="/how-to-start">
                  Read the getting started guide
                </Link>
                .
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </TabsContent>
        <TabsContent value="roster">
          <Accordion type="single" collapsible>
            <AccordionItem value="roster-item">
              <AccordionTrigger>Find Characters</AccordionTrigger>
              <AccordionContent>
                <p className="mb-2">Placeholder details about the roster and how to join.</p>
                <Link className="text-primary underline" to="/roster">
                  Browse the roster
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
