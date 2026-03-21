import os
import requests
import streamlit as st


class NexaAPIClient:
    """Cliente HTTP para a API Nexa."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("NEXA_API_BASE_URL", "http://localhost:8000/api/v1")
        
    def _headers(self):
        token = st.session_state.get("jwt_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
        
    def login(self, username: str, password: str) -> dict:
        """Autenticação OAuth2 Password Flow."""
        url = f"{self.base_url}/auth/token"
        # Passlib/OAuth2 exige envio via form-url-encoded
        data = {"username": username, "password": password}
        try:
            resp = requests.post(url, data=data, timeout=5)
            if resp.status_code == 200:
                payload = resp.json()
                st.session_state["jwt_token"] = payload.get("access_token")
                return {"success": True, "user_id": payload.get("user_id")}
            
            # Tenta pegar erro do JSON, se falhar pega o texto bruto
            try:
                error_msg = resp.json().get("detail", "Erro desconhecido")
            except:
                error_msg = f"Erro HTTP {resp.status_code}: {resp.text[:100]}"
                
            return {"success": False, "error": error_msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def register(self, email: str, password: str, full_name: str | None = None) -> dict:
        """Registra um novo usuário na API (POST /auth/register)."""
        try:
            payload = {"email": email, "password": password, "full_name": full_name}
            resp = requests.post(f"{self.base_url}/auth/register", json=payload, timeout=10)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"success": True, "user_id": data.get("user_id")}

            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"success": False, "error": f"Erro {resp.status_code}: {detail}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_pluggy_token(self) -> dict:
        """Gera um connect token da Pluggy para o frontend exibir o widget."""
        try:
            resp = requests.post(
                f"{self.base_url}/pluggy/connect-token",
                headers=self._headers(),
                timeout=10
            )
            if resp.status_code == 200:
                return {"success": True, "token": resp.json().get("connect_token")}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_pluggy_items(self) -> dict:
        """Lista os items (contas bancárias) conectados pelo usuário via Pluggy."""
        try:
            resp = requests.get(
                f"{self.base_url}/pluggy/items",
                headers=self._headers(),
                timeout=15
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_sandbox_item(self, perf_multiplier: int = 1) -> dict:
        """Cria um item Sandbox (Pluggy Bank) para testes."""
        try:
            resp = requests.post(
                f"{self.base_url}/pluggy/sandbox?perf_multiplier={perf_multiplier}",
                headers=self._headers(),
                timeout=20
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_pluggy_transactions(self) -> dict:
        """Força sincronização das transações Pluggy para o usuário logado."""
        try:
            resp = requests.post(
                f"{self.base_url}/pluggy/sync",
                headers=self._headers(),
                timeout=60,
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_forecast_summary(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/forecast/{user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_goals_summary(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/goals/{user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_budget_advice(self, user_id: str, monthly_income: float = 10000.0) -> dict:
        try:
            url = f"{self.base_url}/budget/{user_id}?monthly_income={monthly_income}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_transactions(self, user_id: str, limit: int = 200) -> dict:
        try:
            url = f"{self.base_url}/transactions/{user_id}?limit={limit}"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_alerts(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/alerts/{user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_subscriptions(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/subscriptions/{user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_health_score_history(self, user_id: str, months: int = 6) -> dict:
        try:
            url = f"{self.base_url}/health-score/history/{user_id}?months={months}"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def post_chat_message(self, user_id: str, message: str) -> dict:
        try:
            url = f"{self.base_url}/chat/"
            payload = {"user_id": user_id, "message": message}
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=60)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_peer_comparison(self, user_id: str, monthly_income: float, history_months: int = 3) -> dict:
        try:
            url = f"{self.base_url}/peers/compare/{user_id}?monthly_income={monthly_income}&history_months={history_months}"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_notifications(self, user_id: str, monthly_income: float = 0.0, include_info: bool = True) -> dict:
        try:
            url = f"{self.base_url}/notifications/{user_id}?monthly_income={monthly_income}&include_info={'true' if include_info else 'false'}"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_fiscal_report(self, user_id: str, year: int, month: int | None = None) -> dict:
        try:
            url = f"{self.base_url}/fiscal-report/{user_id}?year={year}"
            if month:
                url += f"&month={month}"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_fiscal_mixed_use(self, user_id: str, year: int, month: int | None = None) -> dict:
        try:
            url = f"{self.base_url}/fiscal-report/{user_id}/mixed-use?year={year}"
            if month:
                url += f"&month={month}"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_optimizer_cards(self) -> dict:
        try:
            url = f"{self.base_url}/optimizer/cards"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_optimizer_portfolio(self, user_id: str, max_cards: int = 3, monthly_income: float | None = None) -> dict:
        try:
            url = f"{self.base_url}/optimizer/portfolio/{user_id}?max_cards={max_cards}"
            if monthly_income and monthly_income > 0:
                url += f"&monthly_income={monthly_income}"
            resp = requests.get(url, headers=self._headers(), timeout=25)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_optimizer_opportunity_cost(self, user_id: str, current_card_id: str, months: int = 3) -> dict:
        try:
            url = f"{self.base_url}/optimizer/opportunity-cost?user_id={user_id}&current_card_id={current_card_id}&months={months}"
            resp = requests.get(url, headers=self._headers(), timeout=25)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_optimizer_promotions(self) -> dict:
        try:
            url = f"{self.base_url}/optimizer/promotions"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def architect_simulate(self, payload: dict) -> dict:
        try:
            url = f"{self.base_url}/architect/simulate"
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def architect_list_simulations(self, user_id: str, limit: int = 10) -> dict:
        try:
            url = f"{self.base_url}/architect/simulations?user_id={user_id}&limit={limit}"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def architect_metrics(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/architect/metrics?user_id={user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Backward compatibility with older pages/imports.
APIClient = NexaAPIClient
