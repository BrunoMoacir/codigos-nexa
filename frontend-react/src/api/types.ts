// ==================== AUTH ====================
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  full_name?: string;
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
  user_id?: string;
  generated_at?: string;
  period_analyzed_days?: number;
  financial_health?: FinancialHealthData;
  cashflow?: CashflowData;
  safe_to_spend?: SafeToSpendData;
  shadow_invoices?: ShadowInvoiceList;
  monthly_forecasts?: MonthlyForecast[];
}

export interface FinancialHealthData {
  profile_type?: string;
  health_score?: number;
  savings_rate?: number;
  total_income?: number;
  total_expenses?: number;
  monthly_avg_expenses?: number;
  top_categories?: string[];
  trend?: string;
}

export interface CashflowData {
  horizon_days?: number;
  starting_balance?: number;
  ending_balance?: number;
  worst_balance?: number;
  negative_day?: string | null;
  risk_level?: string;
  total_shadow_impact?: number;
  days_at_risk?: number;
}

export interface SafeToSpendData {
  safe_to_spend_total?: number;
  safe_to_spend_daily?: number;
  days?: number;
  risk_level?: string;
  current_balance?: number;
  min_projected_balance?: number;
  total_shadow_invoices?: number;
  safety_buffer?: number;
}

export interface ShadowInvoiceItem {
  type?: 'SUBSCRIPTION' | 'INSTALLMENT';
  description?: string;
  amount?: number;
  next_due_date?: string;
  confidence?: number;
  occurrences?: number | null;
  installment_info?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ShadowInvoiceList {
  invoices?: ShadowInvoiceItem[];
  total_count?: number;
  total_monthly_impact?: number;
  subscriptions_count?: number;
  installments_count?: number;
  total_monthly_committed?: number;
}

export interface MonthlyForecast {
  month: number;
  year: number;
  expected_income: number;
  expected_expenses: number;
  expected_savings: number;
  confidence: number;
  risk_level: string;
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
export type GoalType = 'imovel' | 'viagem' | 'carro' | 'educacao' | 'emergencia' | 'outros';
export type GoalStatus = 'ACTIVE' | 'COMPLETED' | 'ABANDONED';

export interface GoalProjection {
  months_to_complete: number | null;
  monthly_contribution_needed: number;
  completion_date: string | null;
  feasibility: 'EASY' | 'MODERATE' | 'HARD' | 'UNREALISTIC';
  alerts: string[];
}

export interface Goal {
  goal_id: string;
  id?: string;
  user_id: string;
  name: string;
  goal_type: GoalType;
  target_amount: number;
  current_amount: number;
  progress_pct?: number;
  remaining?: number;
  target_date: string | null;
  status: GoalStatus;
  monthly_contribution_needed?: number | null;
  monthly_contribution_actual?: number | null;
  created_at: string;
  updated_at: string;
  projection?: GoalProjection;
}

export interface CreateGoalRequest {
  name: string;
  goal_type?: GoalType;
  target_amount: number;
  current_amount?: number;
  target_date?: string;
}

export interface GoalProgressUpdate {
  amount_to_add: number;
  monthly_actual?: number;
}

export interface GoalsListResponse {
  user_id: string;
  status_filter: string;
  limit: number;
  offset: number;
  total: number;
  goals: Goal[];
  profile_context?: Record<string, unknown>;
}

// ==================== BUDGET ====================
export interface BudgetResponse {
  income: number;
  history_months: number;
  total_expenses_avg: number;
  expenses_pct_income: number;
  savings_gap: number;
  group_summary: {
    group: string;
    current_amount: number;
    current_pct: number;
    target_pct: number;
    suggested_amount: number;
    status: string;
    delta_pct: number;
  }[];
  allocations: {
    category: string;
    group: string;
    current_amount: number;
    current_pct: number;
    suggested_amount: number;
    suggested_pct: number;
    status: string;
  }[];
  actionable_cuts: {
    category: string;
    group: string;
    current: number;
    suggested: number;
    saving: number;
    reasoning: string;
  }[];
  rule_applied: string;
  summary_text: string;
  confidence: number;
  lifestyle_cluster?: string;
  cluster_note?: string;
}

// ==================== CHAT ====================
export interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant' | 'human';
  content: string;
  timestamp?: string;
  created_at?: string;
}

export interface ChatRequest {
  user_id: string;
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  session_id?: string;
  tools_used?: string[];
  latency_ms?: number;
  cost_usd?: number;
}

export interface ChatHistoryItem {
  id: number;
  role: string;
  content: string;
  created_at: string;
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
  income_bracket: string;
  bracket_label: string;
  monthly_income: number;
  user_savings_rate: number;
  benchmark_savings_rate: number;
  savings_percentile_label: string;
  lifestyle_cluster?: string;
  cluster_label?: string;
  benchmark_source?: string;
  categories: {
    category: string;
    label: string;
    user_pct: number;
    benchmark_pct: number;
    user_amount_brl: number;
    benchmark_amount_brl: number;
    delta_pct: number;
    status: string;
    insight: string;
  }[];
  highlights_above: string[];
  highlights_below: string[];
  summary_text: string;
}

// ==================== API ERROR ====================
export interface ApiError {
  detail: string;
  status_code?: number;
}
