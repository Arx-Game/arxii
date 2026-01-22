import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AlertCircle } from 'lucide-react';

export function CharacterCreatePage() {
  const account = useAccount();
  const [activeTab, setActiveTab] = useState('name');

  if (!account) {
    return <Navigate to="/login" replace />;
  }

  if (!account.can_create_characters) {
    return (
      <div className="container max-w-4xl py-8">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              Cannot Create Character
            </CardTitle>
            <CardDescription>
              {!account.email_verified
                ? 'You must verify your email address before creating characters.'
                : 'You are not currently able to create new characters.'}
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="container max-w-6xl py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Create Character</h1>
        <p className="text-muted-foreground">
          Fill out each section to create your character application.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="flex h-auto flex-wrap gap-1">
          <TabsTrigger value="name">Name</TabsTrigger>
          <TabsTrigger value="species">Species</TabsTrigger>
          <TabsTrigger value="homeland">Homeland</TabsTrigger>
          <TabsTrigger value="stats">Stats</TabsTrigger>
          <TabsTrigger value="path">Path</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
          <TabsTrigger value="advantages">Distinctions</TabsTrigger>
          <TabsTrigger value="personality">Personality</TabsTrigger>
          <TabsTrigger value="description">Description</TabsTrigger>
          <TabsTrigger value="background">Background</TabsTrigger>
          <TabsTrigger value="relationships">Relationships</TabsTrigger>
        </TabsList>

        <TabsContent value="name">
          <Card>
            <CardHeader>
              <CardTitle>Character Name</CardTitle>
              <CardDescription>Choose your character's first name.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Name input</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="species">
          <Card>
            <CardHeader>
              <CardTitle>Species</CardTitle>
              <CardDescription>Select your character's species.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Species selection</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="homeland">
          <Card>
            <CardHeader>
              <CardTitle>Homeland</CardTitle>
              <CardDescription>Where does your character come from?</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: City selection</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="stats">
          <Card>
            <CardHeader>
              <CardTitle>Primary Stats</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Stat allocation</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="path">
          <Card>
            <CardHeader>
              <CardTitle>Path</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Path selection</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="skills">
          <Card>
            <CardHeader>
              <CardTitle>Skills</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Skill allocation</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="advantages">
          <Card>
            <CardHeader>
              <CardTitle>Advantages & Disadvantages</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Trait selection</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="personality">
          <Card>
            <CardHeader>
              <CardTitle>Personality</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Personality traits</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="description">
          <Card>
            <CardHeader>
              <CardTitle>Physical Description</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Description fields</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="background">
          <Card>
            <CardHeader>
              <CardTitle>Background</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Background text</p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="relationships">
          <Card>
            <CardHeader>
              <CardTitle>Relationships</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">TODO: Relationship entries</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Submit Application</CardTitle>
          <CardDescription>
            Once all sections are complete, submit your character for review.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            All sections must be marked complete before submission.
          </p>
          <Button disabled>Submit for Review</Button>
        </CardContent>
      </Card>
    </div>
  );
}
