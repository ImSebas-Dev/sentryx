import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/AuthContext'
import Layout from './components/Layout'
import LoginPage     from './pages/LoginPage'
import RegisterPage  from './pages/RegisterPage'
import { VerifyEmailPage, ForgotPasswordPage, ResetPasswordPage } from './pages/AuthPages'
import DashboardPage from './pages/DashboardPage'
import AlertsPage    from './pages/AlertsPage'
import AlertDetailPage from './pages/AlertDetailPage'
import AnalyzePage   from './pages/AnalyzePage'
import { IncidentsPage, ThreatIntelPage } from './pages/OtherPages'
import { Spinner } from './components/UI'
import RetrainingPage from './pages/RetrainingPage'
import PendingUsersPage from './pages/PendingUsersPage'
import ReportsPage from './pages/ReportsPage'
import SecurityPage from './pages/SecurityPage'
import { TermsPage, PrivacyPage, AccessibilityPage } from './pages/LegalPages'

// Guard — redirige al login si no hay sesión
function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="flex items-center justify-center h-screen bg-canvas">
      <Spinner size="lg" />
    </div>
  )
  return user ? children : <Navigate to="/login" replace />
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/accessibility" element={<AccessibilityPage />} />
      <Route path="/*" element={
        <RequireAuth>
          <Layout>
            <Routes>
              <Route index element={<DashboardPage />} />
              <Route path="alerts"              element={<AlertsPage />} />
              <Route path="alerts/:id"          element={<AlertDetailPage />} />
              <Route path="analyze"             element={<AnalyzePage />} />
              <Route path="incidents"           element={<IncidentsPage />} />
              <Route path="threat-intel"        element={<ThreatIntelPage />} />
              <Route path="retraining"          element={<RetrainingPage />} />
              <Route path="reports"             element={<ReportsPage />} />
              <Route path="pending-users"       element={<PendingUsersPage />} />
              <Route path="security"            element={<SecurityPage />} />
              <Route path="*"                   element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        </RequireAuth>
      } />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
