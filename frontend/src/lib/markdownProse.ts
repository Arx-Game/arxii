/**
 * Typography for a block of rendered Markdown (codex prose, mail, item
 * descriptions). `@tailwindcss/typography` is not installed, so a bare `prose`
 * class matches no rule and Tailwind's reset leaves every paragraph with no
 * margin: an author's blank line between paragraphs then shows no gap (#5090).
 * These are the rules that put the gaps, lists and emphasis back. The plugin is
 * not an option while the Almanach owns a `.prose` class of its own.
 */
export const markdownProse = [
  '[&_p]:my-3',
  '[&_p:first-child]:mt-0',
  '[&_p:last-child]:mb-0',
  '[&_strong]:font-semibold',
  '[&_em]:italic',
  '[&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5',
  '[&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5',
  '[&_li]:my-1',
  '[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-muted-foreground',
  '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-sm',
  '[&_a]:text-primary [&_a]:underline-offset-2 hover:[&_a]:underline',
].join(' ');
