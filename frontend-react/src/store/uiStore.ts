import { create } from 'zustand';

interface UIState {
  isSidebarOpen: boolean;
  isLoading: boolean;
  currentPage: string;
  toggleSidebar: () => void;
  setLoading: (loading: boolean) => void;
  setCurrentPage: (page: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  isSidebarOpen: true,
  isLoading: false,
  currentPage: 'home',

  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  setLoading: (loading: boolean) => set({ isLoading: loading }),
  setCurrentPage: (page: string) => set({ currentPage: page }),
}));
