import { SceneDetail } from '../queries';

interface Props {
  scene?: SceneDetail;
}

export function SceneHeader({ scene }: Props) {
  if (!scene) return null;
  return (
    <div>
      <h1 className="mb-2 text-xl font-bold">{scene.name}</h1>
      <p className="mb-4">{scene.description}</p>
      {scene.highlight_message && (
        <div className="mb-4 border bg-muted/20 p-2">
          <p className="font-semibold">Top Message:</p>
          <p>{scene.highlight_message.content}</p>
        </div>
      )}
    </div>
  );
}
