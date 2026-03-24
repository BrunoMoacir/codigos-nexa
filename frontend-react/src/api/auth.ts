import apiClient from './client';
import type { LoginRequest, LoginResponse, RegisterRequest, RegisterResponse } from './types';

/**
 * Login com OAuth2 Password Flow
 */
export const login = async (username: string, password: string): Promise<LoginResponse> => {
  // OAuth2 exige form-urlencoded
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  const response = await apiClient.post<LoginResponse>('/auth/token', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });

  // Salvar token no localStorage
  localStorage.setItem('jwt_token', response.data.access_token);
  localStorage.setItem('user_id', response.data.user_id);

  return response.data;
};

/**
 * Registrar novo usuário
 */
export const register = async (data: RegisterRequest): Promise<RegisterResponse> => {
  const response = await apiClient.post<RegisterResponse>('/auth/register', data);
  return response.data;
};

/**
 * Logout (limpa tokens do localStorage)
 */
export const logout = (): void => {
  localStorage.removeItem('jwt_token');
  localStorage.removeItem('user_id');
};

/**
 * Verificar se usuário está autenticado
 */
export const isAuthenticated = (): boolean => {
  return !!localStorage.getItem('jwt_token');
};

/**
 * Obter user_id do localStorage
 */
export const getUserId = (): string | null => {
  return localStorage.getItem('user_id');
};
