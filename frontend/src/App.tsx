import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { GuestOnlyRoute } from './components/GuestOnlyRoute';
import { ProtectedRoute } from './components/ProtectedRoute';
import { StaffRoute } from './components/StaffRoute';
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
import { RouletteModal } from './components/roulette/RouletteModal';

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
        <Route path="/game" element={<GamePage />} />
        <Route path="/codex" element={<CodexPage />} />
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
          path="/staff/accounts/:id/history"
          element={
            <StaffRoute>
              <StaffAccountHistoryPage />
            </StaffRoute>
          }
        />
        <Route path="/characters/create/application" element={<CharacterCreationPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <RouletteModal />
    </Layout>
  );
}

export default App;
