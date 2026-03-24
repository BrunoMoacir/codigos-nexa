// ==================== AUTH ====================
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface RegisterResponse {
  user_id: string;
  email: string;
}

// ==================== FORECAST ====================
export interface ForecastResponse {
  cashflow: CashflowData;
  safe_to_spend: SafeToSpendData;
  shadow_invoices: ShadowInvoice[];
  health_score: HealthScoreData;
}

export interface CashflowData {
  next_30_days: CashflowDay[];
  summary: {
    total_income: number;
    total_expenses: number;
    net_balance: number;
  };
}

export interface CashflowDay {
  date: string;
  income: number;
  expenses: number;
  balance: number;
}

export interface SafeToSpendData {
  safe_amount: number;
  spent_today: number;
  remaining: number;
  monthly_budget: number;
}

export interface ShadowInvoice {
  id: string;
  description: string;
  amount: number;
  due_date: string;
  status: 'pending' | 'paid' | 'overdue';
}

export interface HealthScoreData {
  score: number;
  trend: 'up' | 'down' | 'stable';
  last_updated: string;
}

// ==================== TRANSACTIONS ====================
export interface Transaction {
  id: string;
  description: string;
  amount: number;
  date: string;
  category: string;
  type: 'income' | 'expense';
  account_id?: string;
}

export interface TransactionsResponse {
  transactions: Transaction[];
  total: number;
}

// ==================== GOALS ====================
export interface Goal {
  id: string;
  user_id: string;
  title: string;
  target_amount: number;
  current_amount: number;
  deadline: string;
  status: 'active' | 'completed' | 'abandoned';
  created_at: string;
}

export interface CreateGoalRequest {
  title: string;
  target_amount: number;
  deadline: string;
}

export interface GoalProgressUpdate {
  amount: number;
}

// ==================== BUDGET ====================
export interface BudgetResponse {
  monthly_income: number;
  suggested_budget: {
    essentials: number;     // 50%
    lifestyle: number;      // 30%
    savings: number;        // 20%
  };
  current_spending: {
    essentials: number;
    lifestyle: number;
    savings: number;
  };
}

// ==================== CHAT ====================
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  tools_used?: string[];
  latency_ms?: number;
  cost_usd?: number;
}

// ==================== PLUGGY ====================
export interface PluggyConnectTokenResponse {
  connect_token: string;
}

export interface PluggyItem {
  id: string;
  connector_name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PluggyItemsResponse {
  items: PluggyItem[];
}

// ==================== ALERTS ====================
export interface Alert {
  id: string;
  type: 'warning' | 'info' | 'danger';
  title: string;
  message: string;
  created_at: string;
}

export interface AlertsResponse {
  alerts: Alert[];
}

// ==================== SUBSCRIPTIONS ====================
export interface Subscription {
  id: string;
  name: string;
  amount: number;
  frequency: 'monthly' | 'yearly';
  next_billing_date: string;
}

export interface SubscriptionsResponse {
  subscriptions: Subscription[];
  total_monthly_cost: number;
}

// ==================== OPTIMIZER ====================
export interface OptimizerAnalysisRequest {
  spending_data: {
    category: string;
    monthly_amount: number;
  }[];
}

export interface CardRecommendation {
  card_name: string;
  issuer: string;
  cashback_rate: number;
  annual_fee: number;
  estimated_benefit: number;
}

export interface OptimizerResponse {
  recommendations: CardRecommendation[];
  current_opportunity_cost: number;
  report_id: string;
}

// ==================== ARCHITECT ====================
export interface ArchitectSimulationRequest {
  goal_amount: number;
  property_value?: number;
  down_payment?: number;
  interest_rate?: number;
  term_months?: number;
}

export interface ArchitectSimulationResponse {
  simulation_id: string;
  financing: {
    total_cost: number;
    monthly_payment: number;
    total_interest: number;
  };
  consortium: {
    total_cost: number;
    monthly_payment: number;
    estimated_wait_months: number;
  };
  saving: {
    months_to_save: number;
    monthly_savings_needed: number;
    opportunity_gain: number;
  };
  recommendation: 'financing' | 'consortium' | 'saving';
}

// ==================== PEERS ====================
export interface PeersComparisonResponse {
  user_spending: number;
  peer_average: number;
  percentile: number;
  insights: string[];
}

// ==================== API ERROR ====================
export interface ApiError {
  detail: string;
  status_code?: number;
}
