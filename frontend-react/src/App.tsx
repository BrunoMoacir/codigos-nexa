import type { ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { RequireAuth } from './components/layout/AuthGuard';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { VerifyEmailPage } from './pages/VerifyEmailPage';
import { ChatPage } from './pages/ChatPage';
import { FeedPage } from './pages/FeedPage';
import { OrganizarPage } from './pages/OrganizarPage';
import { HomePage } from './pages/HomePage';
import { DashboardPage } from './pages/DashboardPage';
import { StrategiesPage } from './pages/StrategiesPage';
import { ConnectionsPage } from './pages/ConnectionsPage';
import { GoalsPage } from './pages/GoalsPage';
import { ProfilePage } from './pages/ProfilePage';
import { WidgetPage } from './pages/WidgetPage';
import { ContactPage } from './pages/ContactPage';
import { DefensePage } from './pages/DefensePage';
import { RightsPage } from './pages/RightsPage';
import { TaxPage } from './pages/TaxPage';
import { WrappedPage } from './pages/WrappedPage';
import { PlansPage } from './pages/PlansPage';
import { session } from './api/session';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5 * 60 * 1000 },
  },
});

const privada = (el: ReactNode) => <RequireAuth>{el}</RequireAuth>;

/** Quem já tem sessão não precisa ver o login de novo. */
const Raiz = () => <Navigate to={session.isActive ? '/dashboard' : '/login'} replace />;

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: '#1A1614',
            color: '#F3EFEA',
            borderRadius: '12px',
            border: '1px solid rgba(212,168,32,0.2)',
            fontSize: '0.85rem',
            fontFamily: "'Satoshi', system-ui, sans-serif",
          },
          success: { iconTheme: { primary: '#2EC8A4', secondary: '#0C0A08' } },
          error:   { iconTheme: { primary: '#F07A64', secondary: '#0C0A08' } },
        }}
      />
      <BrowserRouter>
        <Routes>
          {/* Públicas */}
          <Route path="/login"           element={<LoginPage />} />
          <Route path="/register"        element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password"  element={<ResetPasswordPage />} />
          <Route path="/verify-email"    element={<VerifyEmailPage />} />
          <Route path="/contact"         element={<ContactPage />} />

          {/* HIVE — abas principais */}
          <Route path="/dashboard" element={privada(<DashboardPage />)} />
          <Route path="/chat"      element={privada(<ChatPage />)} />
          <Route path="/feed"      element={privada(<FeedPage />)} />
          <Route path="/organizar" element={privada(<OrganizarPage />)} />

          {/* Ferramentas */}
          <Route path="/strategies" element={privada(<StrategiesPage />)} />
          <Route path="/goals"      element={privada(<GoalsPage />)} />
          <Route path="/defesa"     element={privada(<DefensePage />)} />
          <Route path="/direitos"   element={privada(<RightsPage />)} />
          <Route path="/impostos"   element={privada(<TaxPage />)} />
          <Route path="/wrapped"    element={privada(<WrappedPage />)} />

          {/* Conta */}
          <Route path="/connections" element={privada(<ConnectionsPage />)} />
          <Route path="/planos"      element={privada(<PlansPage />)} />
          <Route path="/profile"     element={privada(<ProfilePage />)} />

          {/* Legadas e utilitárias */}
          <Route path="/home"   element={privada(<HomePage />)} />
          <Route path="/widget" element={privada(<WidgetPage />)} />

          <Route path="/"  element={<Raiz />} />
          <Route path="*"  element={<Raiz />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
