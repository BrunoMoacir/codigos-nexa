import streamlit as st
import time
from utils.ui import load_css
from utils.api import NexaAPIClient

# Redireciona se não estiver logado
if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Por favor, faça login na tela inicial primeiro.")
    st.stop()

st.set_page_config(page_title="Nexa Chat", page_icon="💬", layout="wide")
load_css()

st.title("💬 Chat Inteligente")
st.markdown("Seu Agente de Otimização Financeira, alimentado por IA.")

api = NexaAPIClient()
user_id = st.session_state.username

# Inicializa histórico
if "messages" not in st.session_state:
    st.session_state.messages = []

# Exibe histórico visual
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "meta" in msg:
            st.caption(msg["meta"])

if prompt := st.chat_input("Pergunte sobre seus limites, cartões ou metas..."):
    # Adicionar na tela
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Chamar a API protegida via POST HTTP
    with st.chat_message("assistant"):
        with st.spinner("💭 O Nexa está processando nas camadas do LangGraph..."):
            t0 = time.time()
            resp = api.post_chat_message(user_id, prompt)
            lat = (time.time() - t0) * 1000
            
            if resp.get("success"):
                answer = resp["data"].get("response", "Erro vazio")
                # Extrai as tools inferidas e o custo da resposta via LangGraph (se o backend responder)
                cost_usd = resp["data"].get("cost_usd", None)
                tools_used = resp["data"].get("tools_used", []) 
                
                st.markdown(answer)
                meta_str = f"⏱ {lat:.0f}ms"
                if cost_usd:
                    meta_str += f" | 💰 USD {cost_usd:.5f}"
                if tools_used:
                    meta_str += f" | 🛠 Tools: {', '.join(tools_used)}"
                
                st.caption(meta_str)
                st.session_state.messages.append({"role": "assistant", "content": answer, "meta": meta_str})
            else:
                err = f"⚠️ Falha de comunicação com a API: {resp.get('error')}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
