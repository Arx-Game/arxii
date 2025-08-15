import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export function ProfilePage() {
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Tabs defaultValue="mail" className="w-full">
        <TabsList>
          <TabsTrigger value="mail">Mail</TabsTrigger>
          <TabsTrigger value="media">Media</TabsTrigger>
        </TabsList>
        <TabsContent value="mail">
          <Card>
            <CardHeader>
              <CardTitle>Mail</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Player mail through roster tenures will appear here.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="media">
          <Card>
            <CardHeader>
              <CardTitle>Media Manager</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Upload and manage character galleries. Uploaded media will be scanned for NSFW and
                prohibited content.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
