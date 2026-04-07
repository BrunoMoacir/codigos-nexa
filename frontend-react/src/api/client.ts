import axios from 'axios';
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';

const ENV_API_BASE_URL = String(import.meta.env.VITE_API_URL || '').trim();

export const API_BASE_URL = ENV_API_BASE_URL
  || (import.meta.env.DEV
    ? 'http://localhost:8000/api/v1'
    : 'https://codigos-nexa-production-d3b3.up.railway.app/api/v1');

// Criar instância do Axios
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor de Request: Adicionar JWT token automaticamente
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('jwt_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor de Response: Tratar erros globalmente
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expirado ou inválido
      localStorage.removeItem('jwt_token');
      localStorage.removeItem('user_id');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
