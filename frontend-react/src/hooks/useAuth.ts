import { useMutation, UseMutationResult } from '@tanstack/react-query';
import { login as loginApi, register as registerApi, logout as logoutApi } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import type { LoginResponse, RegisterRequest, RegisterResponse } from '../api/types';

interface UseAuthReturn {
  login: UseMutationResult<LoginResponse, Error, { username: string; password: string }>;
  register: UseMutationResult<RegisterResponse, Error, RegisterRequest>;
  logout: () => void;
  isAuthenticated: boolean;
  userId: string | null;
}

export const useAuth = (): UseAuthReturn => {
  const { setAuth, clearAuth, isAuthenticated, userId } = useAuthStore();

  const loginMutation = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      loginApi(username, password),
    onSuccess: (data) => {
      setAuth(data.access_token, data.user_id);
    },
  });

  const registerMutation = useMutation({
    mutationFn: (data: RegisterRequest) => registerApi(data),
  });

  const logout = () => {
    logoutApi();
    clearAuth();
  };

  return {
    login: loginMutation,
    register: registerMutation,
    logout,
    isAuthenticated,
    userId,
  };
};
