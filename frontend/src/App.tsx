import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { GuestOnlyRoute } from './components/GuestOnlyRoute';
import { ProtectedRoute } from './components/ProtectedRoute';
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
import { ProfilePage } from './pages/ProfilePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { CharacterSheetPage } from './roster/pages/CharacterSheetPage';
import { CharacterCreationPage } from './character-creation';
import { RosterListPage } from './roster/pages/RosterListPage';
import { PlayerMediaPage } from './roster/pages/PlayerMediaPage';
import { SettingsPage } from './pages/SettingsPage';
import { ScenesListPage } from './scenes/pages/ScenesListPage';
import { SceneDetailPage } from './scenes/pages/SceneDetailPage';
import MailPage from './mail/pages/MailPage';
import { XpKudosPage } from './progression/XpKudosPage';
import { EventsListPage } from '@/events/pages/EventsListPage';
import { EventDetailPage } from '@/events/pages/EventDetailPage';
import { EventCreatePage } from '@/events/pages/EventCreatePage';
import { EventEditPage } from '@/events/pages/EventEditPage';
import { CodexPage } from './codex/pages/CodexPage';
import { WardrobePage } from './inventory/pages/WardrobePage';
import { FeedbackPage } from './submissions/pages/FeedbackPage';
import { BugReportPage } from './submissions/pages/BugReportPage';
import { StaffHubPage } from './staff/pages/StaffHubPage';
import { StaffInboxPage } from './staff/pages/StaffInboxPage';
import { StaffApplicationsPage } from './staff/pages/StaffApplicationsPage';
import { StaffApplicationDetailPage } from './staff/pages/StaffApplicationDetailPage';
import { StaffFeedbackPage } from './staff/pages/StaffFeedbackPage';
import { StaffFeedbackDetailPage } from './staff/pages/StaffFeedbackDetailPage';
import { StaffBugReportsPage } from './staff/pages/StaffBugReportsPage';
import { StaffBugReportDetailPage } from './staff/pages/StaffBugReportDetailPage';
import { StaffPlayerReportsPage } from './staff/pages/StaffPlayerReportsPage';
import { StaffPlayerReportDetailPage } from './staff/pages/StaffPlayerReportDetailPage';
import { StaffAccountHistoryPage } from './staff/pages/StaffAccountHistoryPage';
import { StaffGMApplicationsPage } from './staff/pages/StaffGMApplicationsPage';
import { StaffGMApplicationDetailPage } from './staff/pages/StaffGMApplicationDetailPage';
import { RouletteModal } from './components/roulette/RouletteModal';

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
const MuteSettingsPage = lazy(() =>
  import('@/narrative/pages/MuteSettingsPage').then((m) => ({ default: m.MuteSettingsPage }))
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

function App() {
  return (
    <Layout>
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
        <Route path="/profile/*" element={<ProfilePage />}>
          <Route path="mail" element={<MailPage />} />
          <Route path="media" element={<PlayerMediaPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route index element={<Navigate to="mail" replace />} />
        </Route>
        <Route path="/roster" element={<RosterListPage />} />
        <Route path="/characters/create" element={<CharacterCreationPage />} />
        <Route path="/characters/:id" element={<CharacterSheetPage />} />
        <Route path="/scenes" element={<ScenesListPage />} />
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
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
              <XpKudosPage />
            </ProtectedRoute>
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
        <Route path="/game" element={<GamePage />} />
        <Route path="/codex" element={<CodexPage />} />
        <Route
          path="/wardrobe"
          element={
            <ProtectedRoute>
              <WardrobePage />
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
          path="/narrative/mute-settings"
          element={
            <Suspense fallback={<PageLoadingFallback />}>
              <ProtectedRoute>
                <MuteSettingsPage />
              </ProtectedRoute>
            </Suspense>
          }
        />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <RouletteModal />
    </Layout>
  );
}

export default App;
