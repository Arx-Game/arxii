import { ConnectedAccounts } from '@/components/ConnectedAccounts';
import { useRealmTheme } from '@/components/realm-theme-provider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useSetAppearOffline, useVisibilitySettings } from '@/roster/visibility';

function VisibilityPreferences() {
  const { data, isLoading, isError } = useVisibilitySettings();
  const setAppearOffline = useSetAppearOffline();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Visibility</CardTitle>
        <CardDescription>Control how your active character appears to others.</CardDescription>
      </CardHeader>
      <CardContent>
        {isError ? (
          <p className="text-sm text-muted-foreground" data-testid="visibility-no-character">
            Play a character to manage its visibility.
          </p>
        ) : (
          <div className="flex items-center justify-between">
            <div className="pr-4">
              <Label htmlFor="appear-offline">Quiet (hidden) mode</Label>
              <p className="text-sm text-muted-foreground">
                When on, you don&apos;t appear in <code>where</code>/<code>who</code> and can&apos;t
                be paged except by your allowlist. Mail, missions, channels, and same-room presence
                are unaffected.
              </p>
            </div>
            <Switch
              id="appear-offline"
              checked={data?.appear_offline ?? false}
              disabled={isLoading || setAppearOffline.isPending}
              onCheckedChange={(next) => setAppearOffline.mutate(next)}
              aria-label="Quiet (hidden) mode"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

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
      <VisibilityPreferences />
      <ThemePreferences />
      <ConnectedAccounts />
    </div>
  );
}
