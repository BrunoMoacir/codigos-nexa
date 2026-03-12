import streamlit as st
import base64

def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""

def load_css():
    """
    Injeta CSS customizado no Streamlit para criar um visual moderno,
    glassmorphism e botões responsivos.
    """
    custom_css = """
    <style>
    /* Estilo de fundo e fontes globais */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
        font-family: 'Inter', sans-serif;
    }
    
    /* Customização do Sidebar */
    [data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #30363D;
    }
    
    /* Glassmorphism Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 24px;
        backdrop-filter: blur(10px);
        margin-bottom: 16px;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .glass-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(0,0,0,0.3);
    }
    
    /* Customização de Títulos */
    h1, h2, h3 {
        color: #E2E8F0;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    /* Botões Modernos */
    .stButton > button {
        background: linear-gradient(135deg, #667EEA 0%, #764BA2 100%);
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        opacity: 0.9;
        transform: scale(1.02);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    
    /* Input Fields */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #4A5568;
        background-color: #1A202C;
        color: #E2E8F0;
    }
    .stTextInput > div > div > input:focus {
        border-color: #667EEA;
        box-shadow: 0 0 0 1px #667EEA;
    }
    
    /* Esconder branding do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Ajustes específicos do Chat */
    .stChatMessage {
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    [data-testid="chatAvatarIcon-user"] {
        background-color: #4A5568 !important;
    }
    [data-testid="chatAvatarIcon-assistant"] {
        background-color: #667EEA !important;
    }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)
