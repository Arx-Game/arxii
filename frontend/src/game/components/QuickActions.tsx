export function QuickActions() {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-2 font-semibold">Quick Actions</h3>
      <div className="space-y-2">
        <button className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent">Look</button>
        <button className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent">
          Inventory
        </button>
        <button className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent">Who</button>
      </div>
    </div>
  );
}
