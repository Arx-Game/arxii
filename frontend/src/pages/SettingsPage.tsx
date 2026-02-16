import { ConnectedAccounts } from '@/components/ConnectedAccounts';
import { useRealmTheme } from '@/components/realm-theme-provider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

function ThemePreferences() {
  const { plainMode, setPlainMode } = useRealmTheme();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Theme Preferences</CardTitle>
        <CardDescription>Control visual theming across the site.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="plain-mode">Plain mode</Label>
            <p className="text-sm text-muted-foreground">
              Disables realm visual themes, textures, and display fonts.
            </p>
          </div>
          <Switch id="plain-mode" checked={plainMode} onCheckedChange={setPlainMode} />
        </div>
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  return (
    <div className="mt-4 space-y-6">
      <ThemePreferences />
      <ConnectedAccounts />
    </div>
  );
}
