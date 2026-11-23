import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ChatPage } from './pages/ChatPage';
import { FeedPage } from './pages/FeedPage';
import { OrganizarPage } from './pages/OrganizarPage';
import { AddCardPage } from './pages/AddCardPage';
import { HomePage } from './pages/HomePage';
import { StrategiesPage } from './pages/StrategiesPage';
import { ConnectionsPage } from './pages/ConnectionsPage';
import { GoalsPage } from './pages/GoalsPage';
import { ProfilePage } from './pages/ProfilePage';
import { WidgetPage } from './pages/WidgetPage';
import { ContactPage } from './pages/ContactPage';
import { PonteNativa } from './native/PonteNativa';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { VerifyEmailPage } from './pages/VerifyEmailPage';
import { DefensePage } from './pages/DefensePage';
import { RightsPage } from './pages/RightsPage';
import { TaxPage } from './pages/TaxPage';
import { WrappedPage } from './pages/WrappedPage';
import { PlansPage } from './pages/PlansPage';
import { RequireAuth } from './components/layout/AuthGuard';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5 * 60 * 1000 },
  },
});


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
        {/* app nativo (Capacitor): push, widget, links externos, botão voltar — não desenha nada */}
        <PonteNativa />
        <Routes>
          <Route path="/login"    element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          {/* links dos e-mails de recuperação de senha e de verificação */}
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password"  element={<ResetPasswordPage />} />
          <Route path="/verify-email"    element={<VerifyEmailPage />} />

          {/* HIVE — 3 abas principais */}
          <Route path="/chat"      element={<ChatPage />} />
          <Route path="/feed"      element={<FeedPage />} />
          <Route path="/organizar" element={<OrganizarPage />} />
          <Route path="/organizar/cartao/novo" element={<AddCardPage />} />

          {/* Páginas legadas mantidas */}
          <Route path="/home"        element={<HomePage />} />
          <Route path="/goals"       element={<GoalsPage />} />
          <Route path="/strategies"  element={<StrategiesPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/profile"     element={<ProfilePage />} />
          <Route path="/widget"      element={<WidgetPage />} />

          <Route path="/contact" element={<ContactPage />} />

          {/* Ferramentas (acesso pelo Perfil) */}
          <Route path="/defesa"   element={<RequireAuth><DefensePage /></RequireAuth>} />
          <Route path="/direitos" element={<RequireAuth><RightsPage /></RequireAuth>} />
          <Route path="/impostos" element={<RequireAuth><TaxPage /></RequireAuth>} />
          <Route path="/wrapped"  element={<RequireAuth><WrappedPage /></RequireAuth>} />
          <Route path="/planos"   element={<RequireAuth><PlansPage /></RequireAuth>} />

          {/* Dashboard foi descontinuado — Organizar cobre o mesmo escopo com dados reais */}
          <Route path="/dashboard" element={<Navigate to="/organizar" replace />} />

          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
