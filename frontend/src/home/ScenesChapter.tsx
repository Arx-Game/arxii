/**
 * ScenesChapter — "Chapter the Third: Of the Testaments" (#3305).
 *
 * The scene-record excerpt is live (`useSceneExcerpt()`) and omitted
 * entirely when the hook resolves null (no public scene with visible poses
 * to show). The testament blockquote below it is static curated lore, not
 * agent-drafted, so it renders unconditionally and carries no PLACEHOLDER
 * marker.
 */

import { Link } from 'react-router-dom';
import type { SceneListItem } from '@/scenes/types';
import { useSceneExcerpt } from './queries';

export function ScenesChapter() {
  const excerpt = useSceneExcerpt();
  const data = excerpt.data;

  return (
    <div className="gatefold-leaf" id="scenes">
      <div className="gatefold-leaf-main">
        <span className="gatefold-chapter-no">Chapter the Third</span>
        <h2>Of the Testaments</h2>
        <div className="gatefold-leaf-body">
          {/* Apostate's prose, verbatim (#3723). */}
          <p>
            All public roleplay is viewable, with anyone able to browse records of journals, scenes
            and events. Feel free to look through the latest roleplay.
          </p>
        </div>
        {data && (
          <article className="gatefold-scene-record">
            <h3>{data.scene.name}</h3>
            {data.poses.map((pose) => (
              // Rendered plain — strip nothing from player-authored pose content.
              <p key={pose.id} className="gatefold-pose">
                {pose.content}
              </p>
            ))}
            <span className="gatefold-scene-meta">{sceneMetaLine(data.scene)}</span>
          </article>
        )}
        <div className="gatefold-testament">
          <blockquote>
            “I must have hope. There are so few of us left. My covenant was not called, and we are
            one of the last. But there have yet been Glimpses among the young. In time their Durance
            may begin. I must have hope.”
          </blockquote>
          <cite>The last white journal of Perenna · Taken by the Vanishing</cite>
        </div>
        <p className="gatefold-more-line">
          <Link to="/scenes">
            Read the public scenes <span aria-hidden="true">→</span>
          </Link>
        </p>
      </div>
      <aside>
        {/* Apostate's prose, verbatim (#3723). */}
        <span className="gatefold-note">
          <b>Public scenes</b> are open to any reader. You can see how people are engaging with the
          world before you choose or design a character.
        </span>
      </aside>
    </div>
  );
}

/** Builds the "A public scene in <location> · N players · <date>" meta line. */
function sceneMetaLine(scene: SceneListItem): string {
  const parts: string[] = [];
  parts.push(scene.location ? `A public scene in ${scene.location.name}` : 'A public scene');
  const count = scene.participants.length;
  parts.push(`${count} ${count === 1 ? 'player' : 'players'}`);
  parts.push(new Date(scene.date_started).toLocaleDateString());
  return parts.join(' · ');
}
