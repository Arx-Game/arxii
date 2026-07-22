import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate, useParams } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { GuestOnlyRoute } from './components/GuestOnlyRoute';
import { ProtectedRoute } from './components/ProtectedRoute';
import { RequireCharacter } from './components/RequireCharacter';
import { StaffRoute } from './components/StaffRoute';
import { Skeleton } from './components/ui/skeleton';
import { HomePage } from './evennia_replacements/HomePage';
import { GamePage } from './game/GamePage';
import { LoginPage } from './evennia_replacements/LoginPage';
import { RegisterPage } from './evennia_replacements/RegisterPage';
import { EmailVerificationPendingPage } from './evennia_replacements/EmailVerificationPendingPage';
import { EmailVerifyPage } from './evennia_replacements/EmailVerifyPage';
import { AuthCallbackPage } from './evennia_replacements/AuthCallbackPage';
import { UnverifiedAccountPage } from './pages/UnverifiedAccountPage';
import { HowToStartPage } from './pages/HowToStartPage';
import { ProfilePage } from './pages/ProfilePage';
import { BlocksSettingsPage } from './social/pages/BlocksSettingsPage';
import { MutesSettingsPage } from './social/pages/MutesSettingsPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { CharacterSheetPage } from './roster/pages/CharacterSheetPage';
import { CharacterCreationPage } from './character-creation';
import { RosterListPage } from './roster/pages/RosterListPage';
import { PlayerMediaPage } from './roster/pages/PlayerMediaPage';
import { SettingsPage } from './pages/SettingsPage';
import { ScenesListPage } from './scenes/pages/ScenesListPage';
import { TidingsPage } from './tidings/pages/TidingsPage';
import { JournalPage } from './missions/pages/JournalPage';
import { SceneDetailPage } from './scenes/pages/SceneDetailPage';
import { BattleMapPage } from './battles/pages/BattleMapPage';
import { BattleWriteupPage } from './battles/pages/BattleWriteupPage';
import MailPage from './mail/pages/MailPage';
import { XpKudosPage } from './progression/XpKudosPage';
import { EventsListPage } from '@/events/pages/EventsListPage';
import { EventDetailPage } from '@/events/pages/EventDetailPage';
import { EventCreatePage } from '@/events/pages/EventCreatePage';
import { EventEditPage } from '@/events/pages/EventEditPage';
import { CodexPage } from './codex/pages/CodexPage';
import { WardrobePage } from './inventory/pages/WardrobePage';
import { ReclamationPage } from './reclamation/pages/ReclamationPage';
import { MarketPage } from './market/MarketPage';
import { FeedbackPage } from './submissions/pages/FeedbackPage';
import { BugReportPage } from './submissions/pages/BugReportPage';
import { PetitionPage } from './submissions/pages/PetitionPage';
import { PlayerReportPage } from './submissions/pages/PlayerReportPage';
import { StaffHubPage } from './staff/pages/StaffHubPage';
const MissionBrowserPage = lazy(() =>
  import('@/missions/pages/MissionBrowserPage').then((m) => ({
    default: m.MissionBrowserPage,
  }))
);
const MissionCanvasPage = lazy(() =>
  import('@/missions/pages/MissionCanvasPage').then((m) => ({
    default: m.MissionCanvasPage,
  }))
);
const MissionNodePage = lazy(() =>
  import('@/missions/pages/NodePage').then((m) => ({ default: m.NodePage }))
);
const MissionOptionPage = lazy(() =>
  import('@/missions/pages/OptionPage').then((m) => ({ default: m.OptionPage }))
);
const CreateMissionPage = lazy(() =>
  import('@/missions/pages/CreateMissionPage').then((m) => ({
    default: m.CreateMissionPage,
  }))
);
const NPCRolesLibraryPage = lazy(() =>
  import('@/npc_services/pages/NPCRolesLibraryPage').then((m) => ({
    default: m.NPCRolesLibraryPage,
  }))
);
const NPCRoleEditorPage = lazy(() =>
  import('@/npc_services/pages/NPCRoleEditorPage').then((m) => ({
    default: m.NPCRoleEditorPage,
  }))
);
const TriggerGiversPage = lazy(() =>
  import('@/missions/pages/TriggerGiversPage').then((m) => ({
    default: m.TriggerGiversPage,
  }))
);
const WorldBuilderPage = lazy(() =>
  import('@/world-builder/pages/WorldBuilderPage').then((m) => ({
    default: m.WorldBuilderPage,
  }))
);
const StoryBuilderPage = lazy(() =>
  import('@/story-builder/pages/StoryBuilderPage').then((m) => ({
    default: m.StoryBuilderPage,
  }))
);
const StoryRoomsPage = lazy(() =>
  import('@/story-rooms/pages/StoryRoomsPage').then((m) => ({
    default: m.StoryRoomsPage,
  }))
);
import { StaffInboxPage } from './staff/pages/StaffInboxPage';
import { StaffApplicationsPage } from './staff/pages/StaffApplicationsPage';
import { StaffApplicationDetailPage } from './staff/pages/StaffApplicationDetailPage';
import { StaffFeedbackPage } from './staff/pages/StaffFeedbackPage';
import { StaffFeedbackDetailPage } from './staff/pages/StaffFeedbackDetailPage';
import { StaffBugReportsPage } from './staff/pages/StaffBugReportsPage';
import { StaffBugReportDetailPage } from './staff/pages/StaffBugReportDetailPage';
import { StaffPlayerReportsPage } from './staff/pages/StaffPlayerReportsPage';
import { StaffPlayerReportDetailPage } from './staff/pages/StaffPlayerReportDetailPage';
import { StaffSystemErrorsPage } from './staff/pages/StaffSystemErrorsPage';
import { StaffPetitionDetailPage } from './staff/pages/StaffPetitionDetailPage';
import { StaffSystemErrorDetailPage } from './staff/pages/StaffSystemErrorDetailPage';
import { StaffAccountHistoryPage } from './staff/pages/StaffAccountHistoryPage';
import { StaffGMApplicationsPage } from './staff/pages/StaffGMApplicationsPage';
import { StaffGMApplicationDetailPage } from './staff/pages/StaffGMApplicationDetailPage';
import { RouletteModal } from './components/roulette/RouletteModal';
import { Toaster } from './components/ui/sonner';
import { DuelChallengeNotifier } from './combat/DuelChallengeNotifier';
import { ConsentAttentionNotifier } from './scenes/components/ConsentAttentionNotifier';

// ---------------------------------------------------------------------------
// Lazy-loaded stories pages (React.lazy for route-level code splitting)
// ---------------------------------------------------------------------------

const MyActiveStoriesPage = lazy(() =>
  import('@/stories/pages/MyActiveStoriesPage').then((m) => ({ default: m.MyActiveStoriesPage }))
);
const StoryDetailPage = lazy(() =>
  import('@/stories/pages/StoryDetailPage').then((m) => ({ default: m.StoryDetailPage }))
);
const GMQueuePage = lazy(() =>
  import('@/stories/pages/GMQueuePage').then((m) => ({ default: m.GMQueuePage }))
);
const GMDashboardPage = lazy(() =>
  import('@/stories/pages/GMDashboardPage').then((m) => ({ default: m.GMDashboardPage }))
);
const AGMOpportunitiesPage = lazy(() =>
  import('@/stories/pages/AGMOpportunitiesPage').then((m) => ({
    default: m.AGMOpportunitiesPage,
  }))
);
const MyAGMClaimsPage = lazy(() =>
  import('@/stories/pages/MyAGMClaimsPage').then((m) => ({ default: m.MyAGMClaimsPage }))
);
const StaffWorkloadPage = lazy(() =>
  import('@/stories/pages/StaffWorkloadPage').then((m) => ({ default: m.StaffWorkloadPage }))
);
const StoryAuthorPage = lazy(() =>
  import('@/stories/pages/StoryAuthorPage').then((m) => ({ default: m.StoryAuthorPage }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded Phase 5 pages — tables, era admin, browse, mute, GM offers
// ---------------------------------------------------------------------------

const TablesListPage = lazy(() =>
  import('@/tables/pages/TablesListPage').then((m) => ({ default: m.TablesListPage }))
);
const GMUpdateRequestsPage = lazy(() =>
  import('@/sheet_update_requests/pages/GMUpdateRequestsPage').then((m) => ({
    default: m.GMUpdateRequestsPage,
  }))
);
const TableDetailPage = lazy(() =>
  import('@/tables/pages/TableDetailPage').then((m) => ({ default: m.TableDetailPage }))
);
const EraAdminPage = lazy(() =>
  import('@/stories/pages/EraAdminPage').then((m) => ({ default: m.EraAdminPage }))
);
const BrowseStoriesPage = lazy(() =>
  import('@/stories/pages/BrowseStoriesPage').then((m) => ({ default: m.BrowseStoriesPage }))
);
const MyStoryOffersPage = lazy(() =>
  import('@/stories/pages/MyStoryOffersPage').then((m) => ({ default: m.MyStoryOffersPage }))
);
const CrossoverInboxPage = lazy(() =>
  import('@/crossover/pages/CrossoverInboxPage').then((m) => ({
    default: m.CrossoverInboxPage,
  }))
);
const MuteSettingsPage = lazy(() =>
  import('@/narrative/pages/MuteSettingsPage').then((m) => ({ default: m.MuteSettingsPage }))
);
const PrivacyPage = lazy(() =>
  import('@/consent/pages/PrivacyPage').then((m) => ({ default: m.PrivacyPage }))
);
const BoundariesPage = lazy(() =>
  import('@/boundaries/pages/BoundariesPage').then((m) => ({ default: m.BoundariesPage }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded covenants pages
// ---------------------------------------------------------------------------

const CovenantsListPage = lazy(() =>
  import('@/covenants/pages/CovenantsListPage').then((m) => ({
    default: m.CovenantsListPage,
  }))
);

const CovenantDetailPage = lazy(() =>
  import('@/covenants/pages/CovenantDetailPage').then((m) => ({
    default: m.CovenantDetailPage,
  }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded org stub page (#1446, seeds #1884)
// ---------------------------------------------------------------------------

const OrgPage = lazy(() =>
  import('@/orgs/pages/OrgPage').then((m) => ({
    default: m.OrgPage,
  }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded org books pages (#930)
// ---------------------------------------------------------------------------

const BooksShelfPage = lazy(() =>
  import('@/org_books/pages/BooksShelfPage').then((m) => ({
    default: m.BooksShelfPage,
  }))
);

const OrgBooksPage = lazy(() =>
  import('@/org_books/pages/OrgBooksPage').then((m) => ({
    default: m.OrgBooksPage,
  }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded rituals pages
// ---------------------------------------------------------------------------

const RitualsListPage = lazy(() =>
  import('@/rituals/pages/RitualsListPage').then((m) => ({ default: m.RitualsListPage }))
);

const RitualSessionInboxPage = lazy(() =>
  import('@/rituals/pages/RitualSessionInboxPage').then((m) => ({
    default: m.RitualSessionInboxPage,
  }))
);

const RitualSessionDetailPage = lazy(() =>
  import('@/rituals/pages/RitualSessionDetailPage').then((m) => ({
    default: m.RitualSessionDetailPage,
  }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded Thread Hub page, Thread Detail page, and Teaching Offers page
// ---------------------------------------------------------------------------

const ThreadHubPage = lazy(() =>
  import('@/magic/pages/ThreadHubPage').then((m) => ({ default: m.ThreadHubPage }))
);

const ThreadDetailPage = lazy(() =>
  import('@/magic/pages/ThreadDetailPage').then((m) => ({ default: m.ThreadDetailPage }))
);

const SanctumDashboardPage = lazy(() =>
  import('@/magic/pages/SanctumDashboardPage').then((m) => ({
    default: m.SanctumDashboardPage,
  }))
);

const WeavingTeachingOffersPage = lazy(() =>
  import('@/magic/pages/WeavingTeachingOffersPage').then((m) => ({
    default: m.WeavingTeachingOffersPage,
  }))
);

const TechniqueBuilderPage = lazy(() =>
  import('@/magic/pages/TechniqueBuilderPage').then((m) => ({
    default: m.TechniqueBuilderPage,
  }))
);

const AlterationResolutionPage = lazy(() => import('@/magic/pages/AlterationResolutionPage'));

const MagicProgressionPage = lazy(() =>
  import('@/magic/pages/MagicProgressionPage').then((m) => ({
    default: m.MagicProgressionPage,
  }))
);

// ---------------------------------------------------------------------------
// Lazy-loaded journals page (#2160) — diary route, plural /journals. Distinct
// from /missions/journal (the mission ledger, moved there in Task 1).
// ---------------------------------------------------------------------------

const JournalsPage = lazy(() =>
  import('@/journals/pages/JournalsPage').then((m) => ({ default: m.JournalsPage }))
);

// ---------------------------------------------------------------------------
// Suspense fallback — shown while lazy stories chunks load
// ---------------------------------------------------------------------------

function PageLoadingFallback() {
  return (
    <div className="container mx-auto space-y-4 px-4 py-8">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// /scenes/:id/combat redirect (#2197) — combat now renders in-scene via
// CombatRail on SceneDetailPage, so the old dedicated combat route just
// bounces back to the scene, preserving the :id param.
// ---------------------------------------------------------------------------

export function CombatRouteRedirect() {
  const { id } = useParams();
  return <Navigate to={`/scenes/${id}`} replace />;
}

function App() {
  return (
    <Layout>
      {/* Route-level boundary (2026-07 audit): ~130 queries use throwOnError
          with only main.tsx's root boundary above the Layout — one transient
          failure on any unwrapped page replaced the ENTIRE app (nav included)
          with the fallback. Catching inside Layout keeps the chrome alive;
          the root boundary remains the last resort. */}
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route
            path="/login"
            element={
              <GuestOnlyRoute>
                <LoginPage />
              </GuestOnlyRoute>
            }
          />
          <Route
            path="/register"
            element={
              <GuestOnlyRoute>
                <RegisterPage />
              </GuestOnlyRoute>
            }
          />
          <Route path="/register/verify-email" element={<EmailVerificationPendingPage />} />
          <Route path="/verify-email/:key" element={<EmailVerifyPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route path="/account/unverified" element={<UnverifiedAccountPage />} />
          <Route path="/how-to-start" element={<HowToStartPage />} />
          {/* Guarded (2026-07 audit): unauthenticated visits fired the subtree's
            account-scoped queries straight into 403s. */}
          <Route
            path="/profile/*"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          >
            <Route path="mail" element={<MailPage />} />
            <Route path="media" element={<PlayerMediaPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route
              path="privacy"
              element={
                <Suspense fallback={<PageLoadingFallback />}>
                  <PrivacyPage />
                </Suspense>
              }
            />
            <Route
              path="boundaries"
              element={
                <Suspense fallback={<PageLoadingFallback />}>
                  <BoundariesPage />
                </Suspense>
              }
            />
            <Route path="blocks" element={<BlocksSettingsPage />} />
            <Route path="mutes" element={<MutesSettingsPage />} />
            <Route index element={<Navigate to="mail" replace />} />
          </Route>
          <Route path="/roster" element={<RosterListPage />} />
          <Route path="/characters/create" element={<CharacterCreationPage />} />
          <Route path="/characters/:id" element={<CharacterSheetPage />} />
          <Route path="/missions/journal" element={<JournalPage />} />
          <Route
            path="/journals"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <JournalsPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route path="/tidings" element={<TidingsPage />} />
          <Route path="/scenes" element={<ScenesListPage />} />
          <Route path="/scenes/:id" element={<SceneDetailPage />} />
          <Route path="/scenes/:id/combat" element={<CombatRouteRedirect />} />
          <Route path="/scenes/:id/battle" element={<BattleMapPage />} />
          <Route path="/battles/:id" element={<BattleWriteupPage />} />
          <Route path="/events" element={<EventsListPage />} />
          <Route
            path="/events/new"
            element={
              <ProtectedRoute>
                <EventCreatePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/events/:id/edit"
            element={
              <ProtectedRoute>
                <EventEditPage />
              </ProtectedRoute>
            }
          />
          <Route path="/events/:id" element={<EventDetailPage />} />
          <Route
            path="/xp-kudos"
            element={
              <ProtectedRoute>
                <RequireCharacter>
                  <XpKudosPage />
                </RequireCharacter>
              </ProtectedRoute>
            }
          />
          <Route
            path="/story-rooms"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <StoryRoomsPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/feedback"
            element={
              <ProtectedRoute>
                <FeedbackPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/bug-report"
            element={
              <ProtectedRoute>
                <BugReportPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/report-player"
            element={
              <ProtectedRoute>
                <PlayerReportPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/petition"
            element={
              <ProtectedRoute>
                <PetitionPage />
              </ProtectedRoute>
            }
          />
          <Route path="/game" element={<GamePage />} />
          <Route path="/codex" element={<CodexPage />} />
          <Route
            path="/market"
            element={
              <ProtectedRoute>
                <MarketPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/wardrobe"
            element={
              <ProtectedRoute>
                <WardrobePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/reclamation"
            element={
              <ProtectedRoute>
                <ReclamationPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/staff"
            element={
              <StaffRoute>
                <StaffHubPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/inbox"
            element={
              <StaffRoute>
                <StaffInboxPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/missions"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <MissionBrowserPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/missions/new"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <CreateMissionPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/missions/:id/canvas"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <MissionCanvasPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/world-builder"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <WorldBuilderPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/missions/:id/nodes/:nodeId"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <MissionNodePage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/missions/:id/nodes/:nodeId/options/:optionId"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <MissionOptionPage />
                </Suspense>
              </StaffRoute>
            }
          />
          {/* NPC-mediated giver editor lives on the npc-services framework
            (NPCRole + NPCServiceOffer) per #686/#728; trigger-based givers
            (ROOM_TRIGGER + ENVIRONMENTAL_DETAIL) get their own editor — #729. */}
          <Route
            path="/staff/npc-services/roles"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <NPCRolesLibraryPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/npc-services/roles/:id"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <NPCRoleEditorPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/missions/givers"
            element={
              <StaffRoute>
                <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                  <TriggerGiversPage />
                </Suspense>
              </StaffRoute>
            }
          />
          <Route
            path="/staff/applications"
            element={
              <StaffRoute>
                <StaffApplicationsPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/applications/:id"
            element={
              <StaffRoute>
                <StaffApplicationDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/feedback"
            element={
              <StaffRoute>
                <StaffFeedbackPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/feedback/:id"
            element={
              <StaffRoute>
                <StaffFeedbackDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/bug-reports"
            element={
              <StaffRoute>
                <StaffBugReportsPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/bug-reports/:id"
            element={
              <StaffRoute>
                <StaffBugReportDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/player-reports"
            element={
              <StaffRoute>
                <StaffPlayerReportsPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/player-reports/:id"
            element={
              <StaffRoute>
                <StaffPlayerReportDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/system-errors"
            element={
              <StaffRoute>
                <StaffSystemErrorsPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/system-errors/:id"
            element={
              <StaffRoute>
                <StaffSystemErrorDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/petitions/:id"
            element={
              <StaffRoute>
                <StaffPetitionDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/gm-applications"
            element={
              <StaffRoute>
                <StaffGMApplicationsPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/gm-applications/:id"
            element={
              <StaffRoute>
                <StaffGMApplicationDetailPage />
              </StaffRoute>
            }
          />
          <Route
            path="/staff/accounts/:id/history"
            element={
              <StaffRoute>
                <StaffAccountHistoryPage />
              </StaffRoute>
            }
          />
          <Route path="/characters/create/application" element={<CharacterCreationPage />} />

          {/* ------------------------------------------------------------------ */}
          {/* Stories (Phase 4) — lazy-loaded, route-level code splitting         */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/stories"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <Navigate to="my-active" replace />
              </Suspense>
            }
          />
          <Route
            path="/stories/my-active"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <MyActiveStoriesPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/gm-queue"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <GMQueuePage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/gm/dashboard"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <GMDashboardPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/gm/story-builder"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <StoryBuilderPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/agm-opportunities"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <AGMOpportunitiesPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/my-claims"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <MyAGMClaimsPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/staff-workload"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <StaffRoute>
                  <StaffWorkloadPage />
                </StaffRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/author"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <StoryAuthorPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/author/:storyId"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <StoryAuthorPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          {/* /stories/:id must come after the named /stories/* paths */}
          <Route
            path="/stories/:id"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <StoryDetailPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Phase 5 — tables, era admin, browse stories, mute settings, offers  */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/tables"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <TablesListPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/tables/:id"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <TableDetailPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/gm/update-requests"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <GMUpdateRequestsPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/eras"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <StaffRoute>
                  <EraAdminPage />
                </StaffRoute>
              </Suspense>
            }
          />
          <Route
            path="/stories/browse"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <BrowseStoriesPage />
              </Suspense>
            }
          />
          <Route
            path="/stories/my-offers"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <MyStoryOffersPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/crossover/inbox"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <CrossoverInboxPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/narrative/mute-settings"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <MuteSettingsPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Rituals                                                              */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/rituals"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RitualsListPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/rituals/sessions/inbox"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RitualSessionInboxPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/rituals/sessions/:id"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RitualSessionDetailPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Covenants (Slice B Phase 9)                                         */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/covenants"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <CovenantsListPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/covenants/:id"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <CovenantDetailPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Org stub page — click-through destination (#1446, seeds #1884)     */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/orgs/:id"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <OrgPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Org books — the family-books / management screen (#930)            */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/books"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <BooksShelfPage />
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/books/:orgId"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <OrgBooksPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Thread Hub + Thread Detail                                          */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/threads"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RequireCharacter>
                    <ThreadHubPage />
                  </RequireCharacter>
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/threads/teaching"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RequireCharacter>
                    <WeavingTeachingOffersPage />
                  </RequireCharacter>
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/threads/:id"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RequireCharacter>
                    <ThreadDetailPage />
                  </RequireCharacter>
                </ProtectedRoute>
              </Suspense>
            }
          />
          <Route
            path="/sanctums"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RequireCharacter>
                    <SanctumDashboardPage />
                  </RequireCharacter>
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Technique builder                                                   */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/techniques/build"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <TechniqueBuilderPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Magic progression dashboard (#536)                                 */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/magic/progression"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <RequireCharacter>
                    <MagicProgressionPage />
                  </RequireCharacter>
                </ProtectedRoute>
              </Suspense>
            }
          />

          {/* ------------------------------------------------------------------ */}
          {/* Mage Scars — pending alteration resolution (#877)                   */}
          {/* ------------------------------------------------------------------ */}
          <Route
            path="/magic/alterations"
            element={
              <Suspense fallback={<PageLoadingFallback />}>
                <ProtectedRoute>
                  <AlterationResolutionPage />
                </ProtectedRoute>
              </Suspense>
            }
          />

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </ErrorBoundary>
      <RouletteModal />
      <Toaster />
      <DuelChallengeNotifier />
      <ConsentAttentionNotifier />
    </Layout>
  );
}

export default App;
