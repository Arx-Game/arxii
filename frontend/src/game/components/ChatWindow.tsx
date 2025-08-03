import { useAppSelector } from '../../store/hooks'

export function ChatWindow() {
  const { messages, isConnected } = useAppSelector((state) => state.game)

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Game Window</h2>
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
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
    </>
  )
}
