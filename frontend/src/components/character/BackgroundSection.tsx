interface BackgroundSectionProps {
  background?: string;
}

export function BackgroundSection({ background }: BackgroundSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Background</h3>
      <p>{background || 'TBD'}</p>
    </section>
  );
}
