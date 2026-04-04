Instructions to apply the `financial_goals` table to Railway Postgres

1) Open a psql session to your Railway Postgres. With Railway CLI:

   railway run psql --command "\conninfo" 

   or using the connection string (PGHOST/PGUSER/PGPASSWORD/PGDATABASE):

   PGPASSWORD=... psql "postgresql://<user>:<pass>@<host>:<port>/<db>"

2) Run the SQL file located at:

   backend/app/core/db/migrations/005_create_financial_goals_postgres.sql

   Example:

   \i backend/app/core/db/migrations/005_create_financial_goals_postgres.sql

3) Verify the table exists:

   \d financial_goals

4) After applying, redeploy the backend (Railway) so migrations are picked up and the API no longer returns 500 on POST /goals.

If you prefer, run the SQL directly from your CI that has DB access or ask me to commit a small Alembic migration wrapping this SQL.
