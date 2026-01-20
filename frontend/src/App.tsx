import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { GuestOnlyRoute } from './components/GuestOnlyRoute';
import { ProtectedRoute } from './components/ProtectedRoute';
import { HomePage } from './evennia_replacements/HomePage';
import { GamePage } from './game/GamePage';
import { LoginPage } from './evennia_replacements/LoginPage';
import { RegisterPage } from './evennia_replacements/RegisterPage';
import { EmailVerificationPendingPage } from './evennia_replacements/EmailVerificationPendingPage';
import { EmailVerifyPage } from './evennia_replacements/EmailVerifyPage';
import { UnverifiedAccountPage } from './pages/UnverifiedAccountPage';
import { ProfilePage } from './pages/ProfilePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { CharacterSheetPage } from './roster/pages/CharacterSheetPage';
import { CharacterCreationPage } from './character-creation';
import { RosterListPage } from './roster/pages/RosterListPage';
import { PlayerMediaPage } from './roster/pages/PlayerMediaPage';
import { ScenesListPage } from './scenes/pages/ScenesListPage';
import { SceneDetailPage } from './scenes/pages/SceneDetailPage';
import MailPage from './mail/pages/MailPage';
import { XpKudosPage } from './progression/XpKudosPage';

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
        <Route path="/account/unverified" element={<UnverifiedAccountPage />} />
        <Route path="/profile/*" element={<ProfilePage />}>
          <Route path="mail" element={<MailPage />} />
          <Route path="media" element={<PlayerMediaPage />} />
          <Route index element={<Navigate to="mail" replace />} />
        </Route>
        <Route path="/roster" element={<RosterListPage />} />
        <Route path="/characters/create" element={<CharacterCreationPage />} />
        <Route path="/characters/:id" element={<CharacterSheetPage />} />
        <Route path="/scenes" element={<ScenesListPage />} />
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
        <Route
          path="/xp-kudos"
          element={
            <ProtectedRoute>
              <XpKudosPage />
            </ProtectedRoute>
          }
        />
        <Route path="/game" element={<GamePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
