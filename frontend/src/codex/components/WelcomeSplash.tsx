import { BookOpen } from 'lucide-react';
import { useAccount } from '@/store/hooks';

export function WelcomeSplash() {
  const account = useAccount();
  const isLoggedIn = !!account;

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <BookOpen className="mb-4 h-12 w-12 text-muted-foreground" />
      <h2 className="mb-2 text-xl font-semibold">Welcome to the Codex</h2>
      <p className="max-w-md text-muted-foreground">
        {isLoggedIn
          ? 'Browse the knowledge base using the tree on the left, or search for specific topics.'
          : 'The Codex contains generally accessible knowledge, and when you are logged into a character, anything that character has access to. Browse using the tree on the left, or search for specific topics.'}
      </p>
    </div>
  );
}
