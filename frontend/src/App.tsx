import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { HomePage } from './evennia_replacements/HomePage';
import { GamePage } from './game/GamePage';
import { LoginPage } from './evennia_replacements/LoginPage';
import { ProfilePage } from './pages/ProfilePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { CharacterSheetPage } from './pages/CharacterSheetPage';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/characters/:id" element={<CharacterSheetPage />} />
        <Route path="/game" element={<GamePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
