import apiClient from './client';

export const nexaApi = {
  // Dashboard
  getForecast: async (userId: string) => {
    const { data } = await apiClient.get(`/forecast/${userId}`);
    return data;
  },

  getBudget: async (userId: string, monthlyIncome: number) => {
    const { data } = await apiClient.get(`/budget/${userId}`, {
      params: { monthly_income: monthlyIncome },
    });
    return data;
  },

  // Goals (com suporte a paginação e filtros)
  getGoals: async (userId: string, status = 'ACTIVE', limit = 50, offset = 0) => {
    const { data } = await apiClient.get(`/goals/${userId}`, {
      params: { status, limit, offset },
    });
    return data;
  },

  getGoal: async (userId: string, goalId: string) => {
    const { data } = await apiClient.get(`/goals/${userId}/${goalId}`);
    return data;
  },

  createGoal: async (userId: string, goalData: {
    name: string;
    goal_type?: string;
    target_amount: number;
    current_amount?: number;
    target_date?: string;
  }) => {
    const { data } = await apiClient.post(`/goals/${userId}`, goalData);
    return data;
  },

  updateGoalProgress: async (userId: string, goalId: string, payload: {
    amount_to_add: number;
    monthly_actual?: number;
  }) => {
    const { data } = await apiClient.patch(`/goals/${userId}/${goalId}/progress`, payload);
    return data;
  },

  abandonGoal: async (userId: string, goalId: string) => {
    const { data } = await apiClient.delete(`/goals/${userId}/${goalId}`);
    return data;
  },

  getTransactions: async (userId: string, limit = 300, offset = 0) => {
    const { data } = await apiClient.get(`/transactions/${userId}`, {
      params: { limit, offset },
    });
    return data;
  },

  getAlerts: async (userId: string) => {
    const { data } = await apiClient.get(`/alerts/${userId}`);
    return data;
  },

  getSubscriptions: async (userId: string) => {
    const { data } = await apiClient.get(`/subscriptions/${userId}`);
    return data;
  },

  getHealthScoreHistory: async (userId: string, months = 6) => {
    const { data } = await apiClient.get(`/health-score/history/${userId}`, {
      params: { months },
    });
    return data;
  },

  // Pluggy
  createPluggyToken: async () => {
    const { data } = await apiClient.post('/pluggy/connect-token');
    return data;
  },

  getPluggyItems: async () => {
    const { data } = await apiClient.get('/pluggy/items');
    return data;
  },

  createSandboxItem: async (perfMultiplier: number) => {
    const { data } = await apiClient.post('/pluggy/sandbox', null, {
      params: { perf_multiplier: perfMultiplier },
    });
    return data;
  },

  syncPluggyTransactions: async () => {
    const { data } = await apiClient.post('/pluggy/sync');
    return data;
  },

  // Chat
  sendChatMessage: async (userId: string, message: string) => {
    const { data } = await apiClient.post('/chat/', { user_id: userId, message });
    return data;
  },

  getChatHistory: async (userId: string, limit = 50) => {
    const { data } = await apiClient.get('/chat/history', {
      params: { user_id: userId, limit },
    });
    return data;
  },

  // Estrategias
  getOptimizerPortfolio: async (userId: string, maxCards: number, monthlyIncome?: number) => {
    const { data } = await apiClient.get(`/optimizer/portfolio/${userId}`, {
      params: { max_cards: maxCards, monthly_income: monthlyIncome },
    });
    return data;
  },

  getOptimizerCards: async () => {
    const { data } = await apiClient.get('/optimizer/cards');
    return data;
  },

  getOptimizerOpportunityCost: async (userId: string, currentCardId: string, months = 3) => {
    const { data } = await apiClient.get('/optimizer/opportunity-cost', {
      params: { user_id: userId, current_card_id: currentCardId, months },
    });
    return data;
  },

  getOptimizerPromotions: async () => {
    const { data } = await apiClient.get('/optimizer/promotions');
    return data;
  },

  architectSimulate: async (payload: Record<string, unknown>) => {
    const { data } = await apiClient.post('/architect/simulate', payload);
    return data;
  },

  architectListSimulations: async (userId: string, limit = 8) => {
    const { data } = await apiClient.get('/architect/simulations', {
      params: { user_id: userId, limit },
    });
    return data;
  },

  architectMetrics: async (userId: string) => {
    const { data } = await apiClient.get('/architect/metrics', {
      params: { user_id: userId },
    });
    return data;
  },

  getFiscalReport: async (userId: string, year: number, month?: number) => {
    const { data } = await apiClient.get(`/fiscal-report/${userId}`, {
      params: { year, month },
    });
    return data;
  },

  getFiscalMixedUse: async (userId: string, year: number, month?: number) => {
    const { data } = await apiClient.get(`/fiscal-report/${userId}/mixed-use`, {
      params: { year, month },
    });
    return data;
  },

  getPeerComparison: async (userId: string, monthlyIncome?: number, historyMonths: number = 3) => {
    const params: Record<string, unknown> = { history_months: historyMonths };
    if (monthlyIncome && monthlyIncome > 0) params.monthly_income = monthlyIncome;
    const { data } = await apiClient.get(`/peers/compare/${userId}`, { params });
    return data;
  },

  getNotifications: async (userId: string, monthlyIncome?: number, includeInfo = true) => {
    const params: Record<string, unknown> = { include_info: includeInfo };
    if (monthlyIncome && monthlyIncome > 0) params.monthly_income = monthlyIncome;
    const { data } = await apiClient.get(`/notifications/${userId}`, { params });
    return data;
  },

  // F5/F7/F13
  getBankCosts: async (userId: string) => {
    const { data } = await apiClient.get(`/costs/raio-x/${userId}`);
    return data;
  },

  analyzePurchase: async (payload: {
    user_id: string;
    amount: number;
    category: string;
    installments?: number;
    monthly_income?: number;
  }) => {
    const { data } = await apiClient.post('/purchase/analyze', payload);
    return data;
  },

  generateNegotiationScript: async (payload: { user_id: string; bank_name?: string }) => {
    const { data } = await apiClient.post('/negotiator/generate-script', payload);
    return data;
  },
};
