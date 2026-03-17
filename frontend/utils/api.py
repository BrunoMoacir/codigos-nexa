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

    def register(self, username: str, password: str, full_name: str, email: str = "") -> dict:
        """Registra um novo usuário na API."""
        try:
            payload = {
                "username": username,
                "password": password,
                "full_name": full_name,
                "email": email
            }
            resp = requests.post(f"{self.base_url}/auth/register", json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {"success": True, "token": data.get("access_token"), "user_id": data.get("user_id")}
            return {"success": False, "error": f"Erro {resp.status_code}: {resp.json().get('detail', resp.text)}"}
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
