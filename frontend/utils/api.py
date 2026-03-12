import requests
import streamlit as st

class NexaAPIClient:
    """Cliente HTTP para a API Nexa."""
    
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url
        
    def _headers(self):
        token = st.session_state.get("jwt_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
        
    def login(self, username: str, password: str) -> dict:
        """Autenticação OAuth2 Password Flow."""
        url = self.base_url.replace("/api/v1", "/auth/token") # Route is exactly /auth/token
        # Passlib/OAuth2 exige envio via form-url-encoded
        data = {"username": username, "password": password}
        try:
            resp = requests.post(url, data=data, timeout=5)
            if resp.status_code == 200:
                payload = resp.json()
                st.session_state["jwt_token"] = payload.get("access_token")
                return {"success": True}
            return {"success": False, "error": resp.json().get("detail", "Falha no Login")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_forecast_summary(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/forecast/summary?user_id={user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_goals_summary(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/goals/summary?user_id={user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_budget_advice(self, user_id: str) -> dict:
        try:
            url = f"{self.base_url}/budget/advice?user_id={user_id}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"Erro {resp.status_code}"}
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
