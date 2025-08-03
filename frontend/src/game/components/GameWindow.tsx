import { ChatWindow } from './ChatWindow'
import { CommandInput } from './CommandInput'

export function GameWindow() {
  return (
    <div className="rounded-lg border bg-card p-4">
      <ChatWindow />
      <CommandInput />
    </div>
  )
}
