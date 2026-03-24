import { http, HttpResponse } from 'msw';

const API_URL = 'http://localhost:8000/api/v1';

export const handlers = [
  // AUTH - Login
  http.post(`${API_URL}/auth/token`, async ({ request }) => {
    const formData = await request.formData();
    const username = formData.get('username');
    const password = formData.get('password');

    if (username === 'test@email.com' && password === 'password123') {
      return HttpResponse.json({
        access_token: 'fake-jwt-token',
        token_type: 'bearer',
        user_id: 'user-123',
      });
    }

    return new HttpResponse(null, {
      status: 401,
      statusText: 'Invalid credentials',
    });
  }),

  // AUTH - Register
  http.post(`${API_URL}/auth/register`, async ({ request }) => {
    const body = await request.json() as { email: string; password: string };

    if (body.email === 'existing@email.com') {
      return new HttpResponse(
        JSON.stringify({ detail: 'Email already registered' }),
        { status: 400 }
      );
    }

    return HttpResponse.json({
      user_id: 'user-new-123',
      email: body.email,
    }, { status: 201 });
  }),

  // FORECAST
  http.get(`${API_URL}/forecast/:userId`, () => {
    return HttpResponse.json({
      cashflow: {
        next_30_days: [],
        summary: {
          total_income: 10000,
          total_expenses: 7000,
          net_balance: 3000,
        },
      },
      safe_to_spend: {
        safe_amount: 2500,
        spent_today: 150,
        remaining: 2350,
        monthly_budget: 10000,
      },
      shadow_invoices: [],
      health_score: {
        score: 85,
        trend: 'up',
        last_updated: '2026-03-24T10:00:00',
      },
    });
  }),

  // TRANSACTIONS
  http.get(`${API_URL}/transactions/:userId`, () => {
    return HttpResponse.json({
      transactions: [
        {
          id: 'tx-1',
          description: 'Supermercado',
          amount: -150.50,
          date: '2026-03-24',
          category: 'Alimentação',
          type: 'expense',
        },
      ],
      total: 1,
    });
  }),

  // GOALS
  http.get(`${API_URL}/goals/:userId`, () => {
    return HttpResponse.json([
      {
        id: 'goal-1',
        user_id: 'user-123',
        title: 'Viagem',
        target_amount: 5000,
        current_amount: 2500,
        deadline: '2026-12-31',
        status: 'active',
        created_at: '2026-01-01',
      },
    ]);
  }),
];
