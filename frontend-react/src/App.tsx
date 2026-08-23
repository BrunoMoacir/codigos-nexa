import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { LoginPage } from './pages/LoginPage';
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5 * 60 * 1000 },
  },
});

const AuthGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isAuthenticated = !!localStorage.getItem('jwt_token');
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

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
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
          },
          success: { iconTheme: { primary: '#2EC8A4', secondary: '#0C0A08' } },
          error:   { iconTheme: { primary: '#F07A64', secondary: '#0C0A08' } },
        }}
      />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          {/* HIVE — 3 abas principais */}
          <Route path="/chat"      element={<AuthGuard><ChatPage /></AuthGuard>} />
          <Route path="/feed"      element={<AuthGuard><FeedPage /></AuthGuard>} />
          <Route path="/organizar" element={<AuthGuard><OrganizarPage /></AuthGuard>} />

          {/* Páginas legadas mantidas */}
          <Route path="/home"        element={<AuthGuard><HomePage /></AuthGuard>} />
          <Route path="/dashboard"   element={<AuthGuard><DashboardPage /></AuthGuard>} />
          <Route path="/goals"       element={<AuthGuard><GoalsPage /></AuthGuard>} />
          <Route path="/strategies"  element={<AuthGuard><StrategiesPage /></AuthGuard>} />
          <Route path="/connections" element={<AuthGuard><ConnectionsPage /></AuthGuard>} />
          <Route path="/profile"     element={<AuthGuard><ProfilePage /></AuthGuard>} />
          <Route path="/widget"      element={<AuthGuard><WidgetPage /></AuthGuard>} />

          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
