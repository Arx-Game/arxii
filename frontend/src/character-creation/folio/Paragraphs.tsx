/** Blank-line-separated prose as paragraphs (#3630): the one splitter every stage reused inline. */
export function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n\s*\n/).map((para, i) => (
        <p key={i}>{para}</p>
      ))}
    </>
  );
}
