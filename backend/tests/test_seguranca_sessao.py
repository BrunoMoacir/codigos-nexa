"""
Revogação global de sessão e bloqueio de login por conta.

Duas lacunas que a própria doc listava como "próximo degrau":

**1. Trocar a senha não derrubava as sessões abertas.** Quem troca a senha
porque desconfia de invasão espera o contrário. Um access roubado sobrevivia
por até 30 min e — o que importa — um **refresh** roubado por até **14 DIAS**,
porque a rotação continuava emitindo pares novos a partir dele.

A doc dizia que revogar tudo "exigiria claim `iat` + verificação por request".
A verificação já estava sendo paga: `get_current_user` carrega a linha do
usuário para checar `is_active`. O custo real é uma coluna e uma comparação.

**2. O limite de login era só por IP** (10/min). Não segura credential
stuffing distribuído: mil IPs testando dez senhas por minuto na mesma conta
passam inteiros por baixo. `login_throttle` conta por CONTA — e conta pelo
e-mail SUBMETIDO, exista ou não, para o bloqueio não virar oráculo de
existência (que é o que o hash fictício de senha existe para evitar).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import login_throttle
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    sessao_invalidada,
)

BASE = "/api/v1"


# ── 1. O corte de sessão ───────────────────────────────────────────────────

class TestCorteDeSessao:

    def test_token_sem_iat_nunca_e_invalidado(self):
        """Contas antigas e tokens legados seguem valendo até expirar."""
        agora = datetime.now(timezone.utc)
        assert sessao_invalidada(None, agora) is False

    def test_usuario_sem_corte_nunca_invalida(self):
        assert sessao_invalidada(int(time.time()), None) is False

    def test_token_anterior_ao_corte_cai(self):
        corte = datetime.now(timezone.utc)
        emitido_antes = int((corte - timedelta(minutes=5)).timestamp())
        assert sessao_invalidada(emitido_antes, corte) is True

    def test_token_posterior_ao_corte_vale(self):
        corte = datetime.now(timezone.utc)
        emitido_depois = int((corte + timedelta(seconds=5)).timestamp())
        assert sessao_invalidada(emitido_depois, corte) is False

    def test_corte_naive_e_tratado_como_utc(self):
        """Datas sem tzinfo vindas do SQLite não podem virar exceção."""
        corte = datetime.now(timezone.utc).replace(tzinfo=None)
        antes = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        assert sessao_invalidada(antes, corte) is True

    def test_nao_ha_folga_de_um_segundo(self):
        """
        A primeira versão tinha tolerância de 1s, que abria um buraco de um
        segundo inteiro no corte — e o caso que ela "protegia" era justamente
        o token novo e legítimo, que já sobrevive pela comparação estrita.
        """
        corte = datetime.now(timezone.utc).replace(microsecond=0)
        um_segundo_antes = int(corte.timestamp()) - 1
        assert sessao_invalidada(um_segundo_antes, corte) is True

    def test_os_dois_tipos_de_token_carregam_iat(self):
        from jose import jwt

        from app.core.security import ALGORITHM, SECRET_KEY

        for token in (create_access_token({"sub": "u"}), create_refresh_token("u")):
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            assert isinstance(payload.get("iat"), int), payload

    def test_a_janela_que_o_corte_fecha_e_a_do_refresh(self):
        """
        O access já morria em 30 min sozinho. O corte existe pelo refresh.
        """
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert REFRESH_TOKEN_EXPIRE_DAYS == 14


class TestResetDerrubaSessoes:
    """Ponta a ponta contra a API: o reset mata access E refresh."""

    @pytest.fixture
    def cliente(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def conta(self, cliente):
        email = f"corte_{uuid.uuid4().hex[:8]}@nexa.test"
        senha = "SenhaForte@2024"
        resp = cliente.post(f"{BASE}/auth/register", json={"email": email, "password": senha})
        if resp.status_code != 201:
            pytest.skip(f"registro indisponível ({resp.status_code})")
        login_throttle.limpar(email)
        tokens = cliente.post(
            f"{BASE}/auth/token", data={"username": email, "password": senha}
        ).json()
        return {
            "email": email, "senha": senha,
            "user_id": resp.json()["user_id"],
            "access": tokens.get("access_token"),
            "refresh": tokens.get("refresh_token"),
        }

    @staticmethod
    def _resetar(cliente, user_id: str) -> int:
        from app.core.account_tokens import PURPOSE_PASSWORD_RESET, issue_token

        # `iat` tem granularidade de segundo — sem isso o corte cairia dentro
        # do mesmo segundo da emissão e o teste mediria arredondamento.
        time.sleep(1.1)
        return cliente.post(
            f"{BASE}/auth/reset-password",
            json={"token": issue_token(user_id, PURPOSE_PASSWORD_RESET),
                  "new_password": "OutraSenha@2024"},
        ).status_code

    def test_o_access_para_de_valer(self, cliente, conta):
        cabecalho = {"Authorization": f"Bearer {conta['access']}"}
        antes = cliente.get(f"{BASE}/transactions/{conta['user_id']}", headers=cabecalho)
        assert antes.status_code != 401, "token não valia nem antes do reset"

        assert self._resetar(cliente, conta["user_id"]) == 200

        depois = cliente.get(f"{BASE}/transactions/{conta['user_id']}", headers=cabecalho)
        assert depois.status_code == 401, (
            f"access sobreviveu à troca de senha ({depois.status_code})"
        )

    def test_o_refresh_para_de_valer(self, cliente, conta):
        """
        A metade que importa: sem isto, a sessão voltaria no próximo refresh,
        e o refresh vive 14 dias.

        DOIS refresh tokens, de propósito. A primeira versão deste teste usava
        um só: gastava-o para provar que valia "antes" e o testava de novo
        "depois" — mas o refresh é de USO ÚNICO, então o 401 final vinha da
        rotação, não do corte de sessão. Passava com o corte desligado (a
        mutação M25 provou). Um token comprova o "antes"; o outro, intocado,
        é o que mede o corte.
        """
        login_throttle.limpar(conta["email"])
        segundo = cliente.post(
            f"{BASE}/auth/token",
            data={"username": conta["email"], "password": conta["senha"]},
        ).json().get("refresh_token")
        assert segundo and segundo != conta["refresh"]

        # gasta o PRIMEIRO só para provar que refresh funcionava antes
        assert cliente.post(
            f"{BASE}/auth/refresh", json={"refresh_token": conta["refresh"]}
        ).status_code == 200

        assert self._resetar(cliente, conta["user_id"]) == 200

        # o SEGUNDO nunca foi usado: se cair, foi o corte de sessão
        depois = cliente.post(f"{BASE}/auth/refresh", json={"refresh_token": segundo})
        assert depois.status_code == 401, (
            f"refresh sobreviveu à troca de senha ({depois.status_code})"
        )

    def test_a_senha_nova_faz_login(self, cliente, conta):
        """Derrubar sessão não pode derrubar a conta."""
        self._resetar(cliente, conta["user_id"])
        login_throttle.limpar(conta["email"])
        novo = cliente.post(
            f"{BASE}/auth/token",
            data={"username": conta["email"], "password": "OutraSenha@2024"},
        )
        assert novo.status_code == 200
        cabecalho = {"Authorization": f"Bearer {novo.json()['access_token']}"}
        assert cliente.get(
            f"{BASE}/transactions/{conta['user_id']}", headers=cabecalho
        ).status_code != 401


# ── 2. Bloqueio por conta ──────────────────────────────────────────────────

class TestBloqueioDeLoginPorConta:

    @pytest.fixture(autouse=True)
    def _exige_redis(self):
        from app.core.cache import get_redis

        if get_redis() is None:
            pytest.skip("Redis indisponível — o bloqueio é fail-open por desenho")

    def test_conta_bloqueia_no_limite(self):
        email = f"lock_{uuid.uuid4().hex[:8]}@nexa.test"
        login_throttle.limpar(email)
        try:
            for i in range(login_throttle.MAX_TENTATIVAS):
                assert not login_throttle.esta_bloqueada(email), f"bloqueou cedo demais em {i}"
                login_throttle.registrar_falha(email)
            assert login_throttle.esta_bloqueada(email)
        finally:
            login_throttle.limpar(email)

    def test_conta_inexistente_conta_igual(self):
        """
        Se só conta real bloqueasse, o bloqueio responderia "esse e-mail
        existe" — o oráculo que o hash fictício de senha existe para evitar.
        """
        inexistente = f"fantasma_{uuid.uuid4().hex[:8]}@nexa.test"
        login_throttle.limpar(inexistente)
        try:
            for _ in range(login_throttle.MAX_TENTATIVAS):
                login_throttle.registrar_falha(inexistente)
            assert login_throttle.esta_bloqueada(inexistente)
        finally:
            login_throttle.limpar(inexistente)

    def test_login_bem_sucedido_zera(self):
        email = f"lock_{uuid.uuid4().hex[:8]}@nexa.test"
        login_throttle.limpar(email)
        try:
            for _ in range(login_throttle.MAX_TENTATIVAS - 1):
                login_throttle.registrar_falha(email)
            login_throttle.limpar(email)
            assert not login_throttle.esta_bloqueada(email)
        finally:
            login_throttle.limpar(email)

    def test_a_janela_nao_e_renovada_a_cada_falha(self):
        """
        TTL fixado na primeira falha. Renovar a cada tentativa deixaria um
        atacante manter a conta bloqueada para sempre — o bloqueio viraria
        negação de serviço contra o dono.
        """
        from app.core.cache import get_redis

        email = f"lock_{uuid.uuid4().hex[:8]}@nexa.test"
        chave = login_throttle._chave(email)
        cliente = get_redis()
        login_throttle.limpar(email)
        try:
            login_throttle.registrar_falha(email)
            primeiro_ttl = cliente.ttl(chave)
            time.sleep(1.1)
            login_throttle.registrar_falha(email)
            segundo_ttl = cliente.ttl(chave)
            assert segundo_ttl < primeiro_ttl, (
                f"TTL renovado ({primeiro_ttl} → {segundo_ttl}): bloqueio eterno possível"
            )
        finally:
            login_throttle.limpar(email)

    def test_o_email_nunca_e_chave_em_claro(self):
        """Quem lê o Redis não colhe uma lista de e-mails de usuários."""
        email = "pessoa@exemplo.com"
        chave = login_throttle._chave(email)
        assert "pessoa" not in chave and "exemplo" not in chave
        assert chave.startswith("nexa:login_fail:") and len(chave.split(":")[-1]) == 64

    def test_maiusculas_e_espacos_nao_criam_conta_nova(self):
        """Normalizar evita contornar o bloqueio mudando a caixa do e-mail."""
        assert login_throttle._chave(" Pessoa@Exemplo.COM ") == login_throttle._chave(
            "pessoa@exemplo.com"
        )


# ── 3. A catraca de CVE da árvore transitiva ───────────────────────────────

class TestCatracaDeVulnerabilidades:
    """
    O job de CI audita só os pins DIRETOS. A árvore resolvida tinha 156 CVEs em
    33 pacotes — invisíveis. A catraca não paga a dívida; impede a próxima.
    """

    @pytest.fixture(scope="class")
    def base(self) -> dict:
        import json
        import pathlib as _pathlib

        arquivo = _pathlib.Path(__file__).resolve().parents[1] / "security_baseline.json"
        assert arquivo.exists(), "linha de base de CVE ausente"
        return json.loads(arquivo.read_text(encoding="utf-8"))

    def test_a_base_declara_o_que_mede_e_quando(self, base):
        assert base["total_vulnerabilidades"] > 0
        assert base["pacotes_afetados"] > 0
        assert base["medido_em"], "sem data — número sem data envelhece calado"
        assert base["por_pacote"], "sem quebra por pacote não dá para saber o que piorou"

    def test_a_soma_por_pacote_bate_com_o_total(self, base):
        assert sum(base["por_pacote"].values()) == base["total_vulnerabilidades"]

    def test_o_ci_roda_a_catraca(self):
        import pathlib as _pathlib

        ci = (_pathlib.Path(__file__).resolve().parents[2]
              / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "audit_arvore_completa.py" in ci, "catraca não está no CI"

    def test_o_script_existe_e_sabe_atualizar_a_base(self):
        import pathlib as _pathlib

        script = (_pathlib.Path(__file__).resolve().parents[1]
                  / "scripts" / "audit_arvore_completa.py").read_text(encoding="utf-8")
        assert "--atualizar-base" in script
        assert "sys.exit(1)" in script, "catraca que não reprova não é catraca"
