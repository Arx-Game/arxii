import { useSelector } from 'react-redux'
import { RootState } from '../store/store'

export function GamePage() {
  const { isConnected, currentCharacter, messages } = useSelector((state: RootState) => state.game)

  return (
    <div className="mx-auto max-w-4xl">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="rounded-lg border bg-card p-4">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Game Window</h2>
              <div className="flex items-center gap-2">
                <div
                  className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
                />
                <span className="text-sm text-muted-foreground">
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>

            <div className="mb-4 h-96 overflow-y-auto rounded bg-muted/30 p-4">
              {messages.length === 0 ? (
                <p className="text-muted-foreground">No messages yet...</p>
              ) : (
                messages.map((message) => (
                  <div key={message.id} className="mb-2">
                    <span className="text-xs text-muted-foreground">
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </span>
                    <div
                      className={`text-sm ${
                        message.type === 'system'
                          ? 'text-blue-600'
                          : message.type === 'action'
                            ? 'text-green-600'
                            : 'text-foreground'
                      }`}
                    >
                      {message.content}
                    </div>
                  </div>
                ))
              )}
            </div>

            <input
              type="text"
              placeholder="Enter command..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-lg border bg-card p-4">
            <h3 className="mb-2 font-semibold">Character</h3>
            {currentCharacter ? (
              <p className="text-sm">{currentCharacter}</p>
            ) : (
              <p className="text-sm text-muted-foreground">No character selected</p>
            )}
          </div>

          <div className="rounded-lg border bg-card p-4">
            <h3 className="mb-2 font-semibold">Quick Actions</h3>
            <div className="space-y-2">
              <button className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent">
                Look
              </button>
              <button className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent">
                Inventory
              </button>
              <button className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent">
                Who
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
