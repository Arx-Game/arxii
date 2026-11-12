import { ChannelsPanel } from '../components/ChannelsPanel';

export function ChannelsPage() {
  return (
    <div className="container mx-auto max-w-3xl space-y-4 px-4 py-6">
      <h1 className="text-2xl font-semibold">Channels</h1>
      <ChannelsPanel active />
    </div>
  );
}

export default ChannelsPage;
