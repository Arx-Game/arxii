import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { HomePage } from './evennia_replacements/HomePage'
import { GamePage } from './pages/GamePage'
import { LoginPage } from './evennia_replacements/LoginPage'
import { ProfilePage } from './pages/ProfilePage'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/game" element={<GamePage />} />
      </Routes>
    </Layout>
  )
}

export default App
