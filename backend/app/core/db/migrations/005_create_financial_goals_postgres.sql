-- PostgreSQL migration for financial_goals (Railway production)
-- Run in Postgres (psql) against the production database

CREATE TABLE IF NOT EXISTS financial_goals (
  goal_id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  name TEXT NOT NULL,
  goal_type TEXT DEFAULT 'outros',
  target_amount NUMERIC NOT NULL,
  current_amount NUMERIC DEFAULT 0,
  target_date DATE,
  monthly_contribution_needed NUMERIC,
  monthly_contribution_actual NUMERIC,
  status TEXT DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_financial_goals_user_status ON financial_goals(user_id, status);

-- Optional: grant minimal privileges if needed (adjust role)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON financial_goals TO nexadb_user;
