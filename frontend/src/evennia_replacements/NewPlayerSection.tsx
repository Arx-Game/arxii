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
                  Arx II is a collaborative roleplaying game: you play a character in a shared
                  story, scene by scene, alongside other players. No downloads — everything happens
                  right here in the browser.
                </p>
                <p>
                  <Link className="text-primary underline" to="/how-to-start">
                    Learn how to start
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
                <p className="mb-2">
                  Register an account, get a character — apply for an existing roster character or
                  create your own — then join a scene and play. The game teaches you the rest as you
                  go.
                </p>
                <Link className="text-primary underline" to="/how-to-start">
                  Read the step-by-step guide
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
                <p className="mb-2">
                  The roster is a cast of established characters with histories, families, and
                  rivalries already woven into the world. Applying to play one is the fastest way
                  into the story.
                </p>
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
