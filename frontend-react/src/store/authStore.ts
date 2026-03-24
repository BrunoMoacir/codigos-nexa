import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  token: string | null;
  userId: string | null;
  isAuthenticated: boolean;
  setAuth: (token: string, userId: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      userId: null,
      isAuthenticated: false,

      setAuth: (token: string, userId: string) => {
        localStorage.setItem('jwt_token', token);
        localStorage.setItem('user_id', userId);
        set({ token, userId, isAuthenticated: true });
      },

      clearAuth: () => {
        localStorage.removeItem('jwt_token');
        localStorage.removeItem('user_id');
        set({ token: null, userId: null, isAuthenticated: false });
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        userId: state.userId,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
