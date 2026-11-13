import { ChannelsPanel } from '../components/ChannelsPanel';
import { useGameSocketConnected } from '../queries';

export function ChannelsPage() {
  // With a game socket open (kept across navigation) frames arrive live; without one, poll.
  const socketConnected = useGameSocketConnected();
  return (
    <div className="container mx-auto max-w-3xl space-y-4 px-4 py-6">
      <h1 className="text-2xl font-semibold">Channels</h1>
      <ChannelsPanel active poll={!socketConnected} />
    </div>
  );
}

export default ChannelsPage;
