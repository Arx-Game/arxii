/**
 * HouseDocument (#3983 Task 9, plates S-III to S-VIII) — the House
 * Document's route element: the top bar (with the publish `.status` chip),
 * the contents rail (House: The House / The Family; Holdings: Realm /
 * Lands with barony sub-entries / Estate), the chapter for the current
 * leaf, and the record rail. Task 8's `HouseDocumentStub` in `AlmanachPage`
 * is replaced by this component.
 *
 * Leaf selection is local component state, not `?leaf=` in the URL (#3983
 * Task 9 decision 1's either/or) — matching `RealmLadderPage`'s own
 * `pressedTier` choice one plate over, and there's no cross-session/shared
 * link a URL-synced leaf would serve here that local state doesn't already
 * (unlike the ladder's tier, which IS worth deep-linking to for a shared
 * "look at this rung" link — a house's own chapters aren't shared that way).
 *
 * Clicking the bar's `.status` chip opens a sixth, `RecordRail`-less leaf
 * ("publish") — plate VIII's own contents rail never lists a "Publish"
 * entry among House/Family/Realm/Lands/Estate, and its `.almanac` drops to
 * two grid columns (no aside), so a leaf reached a different way than the
 * other five, dropping the rail entirely, matches the plate better than
 * inventing a sixth contents-rail row the plate doesn't draw.
 *
 * Every `RecordRail` row below either reuses a REAL field the document
 * carries or is a plate-labeled row with a stated dash — see each leaf's
 * own top comment for the specific field-level gaps (house "kind"/
 * nobility-tier, realm tier/treasury/pacts, family kind/influence/
 * recognition/kin-slots, barony unrest/defenses/garrison — none of these
 * has a field anywhere in `HouseDocument`). Every leaf's plate also gets its
 * "doors" section now (review fix round 1, Finding I2): a door with a real
 * destination is a working `Link`/button; one with none yet (the house on
 * the roster, the public tree, the secret editor, Estate's Atlas link)
 * renders as a labeled dash via `RecordRail`'s `doors` support for door
 * entries with neither `to` nor `onClick` — "the ladder" now links to
 * `realm.realm_id`'s own ladder page (final review deferred item 3) and
 * only dashes when a house's realm carries no id. Family
 * additionally gets the plate's "linked houses" section (`extraSection`) —
 * present on the page per the plate, its rows dashed for the same reason
 * (no secondary-membership data on the wire).
 */
import { useState, type ReactNode } from 'react';

import { useAlmanachMutation, useHouseDocument } from '../queries';
import { PUBLISH_STATUS } from '../copy';
import { HouseChapter, type EditHouseFields } from './HouseChapter';
import { FamilyChapter } from './FamilyChapter';
import type { CreateKinFields } from './AddKinDialog';
import type { PersonPanelSaveFields } from './PersonPanel';
import { RealmLeaf, type SwearFields } from './RealmLeaf';
import { LandsLeaf } from './LandsLeaf';
import type { DescribeDemesneFields } from './BaronyPage';
import { EstateLeaf, type PlanEstateFields } from './EstateLeaf';
import { PublishBar } from './PublishBar';
import {
  RecordRail,
  type RecordRailDoor,
  type RecordRailRow,
  type RecordRailSection,
} from './RecordRail';
import '../almanach.css';

type Leaf = 'house' | 'family' | 'realm' | 'lands' | 'estate' | 'publish';

function Dash() {
  return <abbr title="none">—</abbr>;
}

export function HouseDocument({ houseId }: { houseId: number }) {
  const { data: doc } = useHouseDocument(houseId);
  const [leaf, setLeaf] = useState<Leaf>('house');

  const editHouse = useAlmanachMutation('almanach_edit_house');
  const editKin = useAlmanachMutation('almanach_edit_kin');
  const swear = useAlmanachMutation('almanach_swear');
  const describeDemesne = useAlmanachMutation('almanach_describe_demesne');
  const planEstate = useAlmanachMutation('almanach_plan_estate');
  const publish = useAlmanachMutation('almanach_publish');

  if (!doc) {
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">Loading the house…</div>
      </div>
    );
  }

  const { house, family, household, realm, lands, estate } = doc;
  const published = house.published_at != null;

  const onSaveHouse = (fields: EditHouseFields) => editHouse.mutate({ org_id: houseId, ...fields });
  const onEditKin = (fields: PersonPanelSaveFields) =>
    editKin.mutate({ org_id: houseId, ...fields });
  const onCreateKin = (fields: CreateKinFields) => editKin.mutate({ ...fields });
  const onSwear = (fields: SwearFields) => swear.mutate({ ...fields });
  const onDescribeDemesne = (domainId: number, fields: DescribeDemesneFields) =>
    describeDemesne.mutate({ domain_id: domainId, ...fields });
  const onPlanEstate = (fields: PlanEstateFields) =>
    planEstate.mutate({ org_id: houseId, ...fields });
  const onPublish = (next: boolean) => publish.mutate({ org_id: houseId, publish: next });

  let chapter: ReactNode = null;
  let recordRows: RecordRailRow[] = [];
  let recordExtraSection: RecordRailSection | undefined;
  let recordDoors: RecordRailDoor[] = [];

  switch (leaf) {
    case 'house':
      chapter = <HouseChapter house={house} realmTheme={realm.realm_theme} onSave={onSaveHouse} />;
      recordRows = [
        { label: 'crown', value: realm.sworn_to !== '' ? realm.sworn_to : <Dash /> },
        { label: 'holds', value: realm.holds !== '' ? realm.holds : <Dash /> },
        {
          label: 'demesne',
          value: `${realm.demesne.length} · seat ${lands.seat !== '' ? lands.seat : 'none'}`,
        },
        { label: 'vassals', value: realm.vassals.length > 0 ? realm.vassals.length : <Dash /> },
        { label: 'stature', value: <Dash /> },
      ];
      recordDoors = [{ label: 'the house on the roster', small: 'as players read it' }];
      break;
    case 'family':
      chapter = (
        <FamilyChapter
          houseId={houseId}
          houseName={house.name}
          family={family}
          household={household}
          onEdit={onEditKin}
          onCreate={onCreateKin}
        />
      );
      recordRows = [
        { label: 'kind', value: <Dash /> },
        { label: 'influence', value: <Dash /> },
        { label: 'recognition', value: <Dash /> },
        { label: 'kin slots', value: <Dash /> },
      ];
      recordExtraSection = {
        heading: 'linked houses',
        rows: [{ label: 'none on record', value: <Dash /> }],
      };
      recordDoors = [
        { label: 'the tree as players see it', small: 'public record only' },
        { label: '✎ the secret', small: 'who knows, what reveals it' },
      ];
      break;
    case 'realm':
      chapter = (
        <RealmLeaf houseId={houseId} houseName={house.name} realm={realm} onSwear={onSwear} />
      );
      recordRows = [
        { label: 'tier', value: <Dash /> },
        { label: 'treasury', value: <Dash /> },
        { label: 'pacts', value: <Dash /> },
      ];
      recordDoors = [
        realm.realm_id != null
          ? { label: 'the ladder', to: `/staff/almanach/realms/${realm.realm_id}` }
          : { label: 'the ladder' },
      ];
      break;
    case 'lands':
      chapter = <LandsLeaf houseName={house.name} lands={lands} onDescribe={onDescribeDemesne} />;
      recordRows = [
        { label: 'count', value: lands.count },
        { label: 'population', value: lands.population > 0 ? lands.population : <Dash /> },
        {
          label: 'produces',
          value: lands.produces.length > 0 ? lands.produces.join(' · ') : <Dash />,
        },
        { label: 'seat', value: lands.seat !== '' ? lands.seat : <Dash /> },
      ];
      recordDoors = [{ label: 'open on the Atlas', to: '/staff/world-builder' }];
      break;
    case 'estate':
      chapter = <EstateLeaf estate={estate} onPlan={onPlanEstate} />;
      recordRows = [{ label: 'kind', value: <Dash /> }];
      recordDoors = [{ label: 'open on the Atlas' }];
      break;
    case 'publish':
      chapter = (
        <PublishBar
          house={house}
          family={family}
          lands={lands}
          estate={estate}
          onPublish={onPublish}
        />
      );
      break;
  }

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          <span>Almanach de Catenys</span>
          <span>{house.name}</span>
        </span>
        <span className="right">
          <button
            type="button"
            className={published ? 'status pub' : 'status'}
            onClick={() => setLeaf('publish')}
          >
            {published ? PUBLISH_STATUS.published : PUBLISH_STATUS.draft}
          </button>
          <span className="mode">staff</span>
        </span>
      </div>
      <div
        className="almanac"
        style={leaf === 'publish' ? { gridTemplateColumns: '13rem minmax(0, 1fr)' } : undefined}
      >
        <aside className="contents">
          <div className="mv">
            <span className="label">House</span>
            <ol>
              <li className={leaf === 'house' ? 'cur' : undefined}>
                <button type="button" onClick={() => setLeaf('house')}>
                  The House
                </button>
              </li>
              <li className={leaf === 'family' ? 'cur' : undefined}>
                <button type="button" onClick={() => setLeaf('family')}>
                  The Family
                </button>
              </li>
            </ol>
          </div>
          <div className="mv">
            <span className="label">Holdings</span>
            <ol>
              <li className={leaf === 'realm' ? 'cur' : undefined}>
                <button type="button" onClick={() => setLeaf('realm')}>
                  Realm
                </button>
              </li>
              <li className={leaf === 'lands' ? 'cur' : undefined}>
                <button type="button" onClick={() => setLeaf('lands')}>
                  Lands <small>{lands.count} baronies</small>
                </button>
                {lands.baronies.length > 0 && (
                  <ol>
                    {lands.baronies.map((barony) => (
                      <li key={barony.id}>
                        <button type="button" onClick={() => setLeaf('lands')}>
                          {barony.name}
                        </button>
                      </li>
                    ))}
                  </ol>
                )}
              </li>
              <li className={leaf === 'estate' ? 'cur' : undefined}>
                <button type="button" onClick={() => setLeaf('estate')}>
                  Estate
                </button>
              </li>
            </ol>
          </div>
        </aside>
        {chapter}
        {leaf !== 'publish' && (
          <RecordRail rows={recordRows} extraSection={recordExtraSection} doors={recordDoors} />
        )}
      </div>
    </div>
  );
}
