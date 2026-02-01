import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchConnectedAccounts,
  fetchSocialProviders,
  disconnectSocialAccount,
  initiateSocialLogin,
} from '@/evennia_replacements/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function ConnectedAccounts() {
  const queryClient = useQueryClient();

  // Fetch connected accounts
  const {
    data: connectedAccounts = [],
    isLoading: accountsLoading,
    error: accountsError,
  } = useQuery({
    queryKey: ['connectedAccounts'],
    queryFn: fetchConnectedAccounts,
  });

  // Fetch available providers
  const { data: providers = [] } = useQuery({
    queryKey: ['socialProviders'],
    queryFn: fetchSocialProviders,
  });

  // Disconnect mutation
  const disconnectMutation = useMutation({
    mutationFn: disconnectSocialAccount,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectedAccounts'] });
    },
  });

  // Find providers that aren't connected yet
  const connectedProviderIds = connectedAccounts.map((account) => account.provider);
  const availableProviders = providers.filter(
    (provider) => !connectedProviderIds.includes(provider.id)
  );

  const handleConnect = (providerId: string) => {
    initiateSocialLogin(providerId, 'connect');
  };

  if (accountsLoading) {
    return <div className="py-4">Loading connected accounts...</div>;
  }

  if (accountsError) {
    return <div className="py-4 text-red-600">Failed to load connected accounts.</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connected Accounts</CardTitle>
        <CardDescription>Manage your connected social accounts for easy login.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {connectedAccounts.length === 0 && availableProviders.length === 0 ? (
          <p className="text-muted-foreground">No social login providers are configured.</p>
        ) : (
          <>
            {connectedAccounts.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Connected</h4>
                {connectedAccounts.map((account) => (
                  <div
                    key={account.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div>
                      <span className="font-medium capitalize">{account.provider}</span>
                      <span className="ml-2 text-sm text-muted-foreground">{account.uid}</span>
                    </div>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => disconnectMutation.mutate(account.id)}
                      disabled={disconnectMutation.isPending}
                    >
                      {disconnectMutation.isPending ? 'Disconnecting...' : 'Disconnect'}
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {availableProviders.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Available</h4>
                {availableProviders.map((provider) => (
                  <div
                    key={provider.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <span className="font-medium">{provider.name}</span>
                    <Button variant="outline" size="sm" onClick={() => handleConnect(provider.id)}>
                      Connect
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
