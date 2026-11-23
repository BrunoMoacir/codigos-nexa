"""
O que a auditoria de segurança de 2026-08-25 encontrou, e o que impede a volta.

A arquitetura passou: sonda ao vivo em TODAS as 44 rotas GET com `{user_id}`
devolveu 401/403 — zero vazamento entre contas. O boot recusa produção com
`SECRET_KEY` mock. O desenho de token é cuidadoso.

Os buracos estavam entre o desenho e a operação:

1. **O apagamento LGPD deixava dado para trás.** O inventário era uma lista
   mantida à mão com a instrução "inclua a tabela nova aqui". Errava nos dois
   sentidos: 6 tabelas com `user_id` fora dela (incluindo
   `rejected_transactions`, 200 linhas de dado financeiro, e `auth_tokens`,
   2851) e 5 entradas para tabelas inexistentes, que caíam em `skipped`.

2. **A revogação de token estava inerte fora do docker.** `REDIS_URL` aponta
   para o hostname do compose; fora dele não resolve, `get_redis()` devolvia
   None e `_is_token_revoked` devolvia False para tudo — logout não revogava e
   reuso de refresh não era detectado. Havia um Redis em localhost o tempo todo.

3. **O `--ignore-vuln` do CI cobria 5 de 9 CVEs reportados**, então o job
   reprovava desde antes desta rodada — e um dos ignores era obsoleto.

4. **`validate_user_id` não validava UUID v4** em ambiente nenhum, embora a
   doc afirmasse que sim.

5. **`app/retention/` tinha rota sem autenticação nenhuma**, com dado
   fabricado por `hash(user_id)` e um `pause-account` que respondia "conta
   pausada com sucesso" sem fazer nada. Não estava montada — um
   `include_router` de distância.
"""

from __future__ import annotations

import importlib
import re
import pathlib
import uuid

import pytest

_RAIZ = pathlib.Path(__file__).resolve().parents[1]


# ── 1. O inventário LGPD cobre tudo que tem dado do titular ────────────────

class TestInventarioLGPD:

    def test_toda_tabela_com_user_id_entra_no_inventario(self):
        """
        A guarda que faltava. Uma tabela nova com `user_id` passa a ser
        apagada automaticamente; se alguém decidir que NÃO deve ser, tem de
        dizer isso em `_NAO_APAGAR`, com motivo.
        """
        from sqlalchemy import inspect

        from app.core.database import engine
        from app.privacy.service import _NAO_APAGAR, inventario_de_dados

        inspetor = inspect(engine)
        no_banco = set()
        for tabela in inspetor.get_table_names():
            try:
                colunas = {c["name"] for c in inspetor.get_columns(tabela)}
            except Exception:
                continue
            if "user_id" in colunas:
                no_banco.add(tabela)

        coberto = {t for t, _ in inventario_de_dados()} | set(_NAO_APAGAR)
        fora = sorted(no_banco - coberto)
        assert not fora, f"tabelas com dado do titular fora do apagamento: {fora}"

    def test_users_e_sempre_a_ultima(self):
        """Apagar a conta antes dos dependentes quebraria por chave estrangeira."""
        from app.privacy.service import inventario_de_dados

        inventario = [t for t, _ in inventario_de_dados()]
        if "users" in inventario:
            assert inventario[-1] == "users", inventario[-3:]

    def test_nao_inclui_tabela_inexistente(self):
        """
        O inventário à mão listava 5 tabelas que não existem — elas caíam no
        `except` e viravam `skipped`, indistinguíveis de uma falha real.
        """
        from sqlalchemy import inspect

        from app.core.database import engine
        from app.privacy.service import inventario_de_dados

        existentes = set(inspect(engine).get_table_names())
        fantasmas = [t for t, _ in inventario_de_dados() if t not in existentes]
        assert not fantasmas, fantasmas

    def test_cada_excecao_tem_motivo_escrito(self):
        from app.privacy.service import _NAO_APAGAR

        for tabela, motivo in _NAO_APAGAR.items():
            assert motivo and len(motivo) > 10, f"{tabela} sem motivo"


class TestApagamentoDeVerdade:
    """
    Ponta a ponta contra o banco real, incluindo as três tabelas que antes
    sobreviviam à eliminação.
    """

    @pytest.fixture
    def titular_com_dados(self):
        from sqlalchemy import text

        from app.core.database import SessionLocal

        uid = f"lgpd-teste-{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO transactions_clean (transaction_id,user_id,account_id,"
                    "description,amount,date,transaction_type,category,is_recurring,"
                    "is_installment) VALUES (:t,:u,'acc','MERCADO',-50,'2026-06-01',"
                    "'DEBIT','x',false,false)"
                ),
                {"t": str(uuid.uuid4()), "u": uid},
            )
            db.execute(
                text(
                    "INSERT INTO rejected_transactions (id,user_id,error_type,"
                    "error_message,raw_data,raw_data_truncated,rejected_at,reviewed)"
                    " VALUES (:i,:u,'schema','campo faltando','{}',false,now(),false)"
                ),
                {"i": str(uuid.uuid4()), "u": uid},
            )
            db.execute(
                text(
                    "INSERT INTO auth_tokens (token_hash,user_id,purpose,expires_at)"
                    " VALUES (:h,:u,'reset',now())"
                ),
                {"h": uuid.uuid4().hex, "u": uid},
            )
            db.commit()
        yield uid
        with SessionLocal() as db:
            for t in ("transactions_clean", "rejected_transactions", "auth_tokens"):
                db.execute(text(f"DELETE FROM {t} WHERE user_id=:u"), {"u": uid})
            db.commit()

    @pytest.mark.parametrize(
        "tabela", ["transactions_clean", "rejected_transactions", "auth_tokens"]
    )
    def test_nada_sobrevive(self, titular_com_dados, tabela):
        from sqlalchemy import text

        from app.core.database import SessionLocal
        from app.privacy.service import erase_user_data

        erase_user_data(titular_com_dados)
        with SessionLocal() as db:
            n = db.execute(
                text(f"SELECT COUNT(*) FROM {tabela} WHERE user_id=:u"),
                {"u": titular_com_dados},
            ).scalar()
        assert n == 0, f"{tabela} manteve {n} linha(s) após a eliminação"

    def test_o_export_enxerga_as_mesmas_tabelas(self, titular_com_dados):
        """
        Portabilidade e eliminação são o MESMO inventário: exportar menos do
        que se apaga esconde dado do titular dele mesmo.
        """
        from app.privacy.service import export_user_data

        dados = export_user_data(titular_com_dados)["data"]
        assert {"transactions_clean", "rejected_transactions", "auth_tokens"} <= set(dados)

    def test_nao_toca_em_outro_titular(self, titular_com_dados):
        from sqlalchemy import text

        from app.core.database import SessionLocal
        from app.privacy.service import erase_user_data

        alheio = f"lgpd-alheio-{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO auth_tokens (token_hash,user_id,purpose,expires_at)"
                    " VALUES (:h,:u,'reset',now())"
                ),
                {"h": uuid.uuid4().hex, "u": alheio},
            )
            db.commit()
        try:
            erase_user_data(titular_com_dados)
            with SessionLocal() as db:
                n = db.execute(
                    text("SELECT COUNT(*) FROM auth_tokens WHERE user_id=:u"),
                    {"u": alheio},
                ).scalar()
            assert n == 1, "eliminação vazou para outro titular"
        finally:
            with SessionLocal() as db:
                db.execute(text("DELETE FROM auth_tokens WHERE user_id=:u"), {"u": alheio})
                db.commit()


# ── 2. Revogação de token ──────────────────────────────────────────────────

class TestRevogacaoDeToken:

    def test_revogar_e_verificar_funcionam_juntos(self):
        """
        Fora do docker isto devolvia False para tudo: `REDIS_URL` aponta para
        o hostname do compose, `get_redis()` era None e o fail-open valia
        sempre — logout não revogava.
        """
        from app.core.cache import get_redis
        from app.core.security import _is_token_revoked, revoke_token

        if get_redis() is None:
            pytest.skip("Redis indisponível — fail-open é o comportamento esperado")

        jti = f"teste-{uuid.uuid4().hex}"
        assert _is_token_revoked(jti) is False
        revoke_token(jti, 60)
        assert _is_token_revoked(jti) is True, "revogação não teve efeito"

    def test_o_fallback_de_dev_nao_vale_em_producao(self):
        """
        Em produção, um Redis que não resolve é incidente e tem de aparecer
        como tal — não ser contornado por localhost.
        """
        import app.core.cache as cache
        from app.core.config import settings

        original = settings.APP_ENV, settings.REDIS_URL
        try:
            settings.REDIS_URL = "redis://redis:6379/0"
            settings.APP_ENV = "production"
            assert cache._urls_a_tentar() == ["redis://redis:6379/0"]
            settings.APP_ENV = "development"
            assert len(cache._urls_a_tentar()) == 2
            assert "127.0.0.1" in cache._urls_a_tentar()[1]
        finally:
            settings.APP_ENV, settings.REDIS_URL = original

    def test_a_janela_do_fail_open_esta_declarada_corretamente(self):
        """
        O docstring dizia "TTL máximo de 24h garante expiração natural". O
        refresh vive 14 DIAS e a rotação o revoga pelo tempo restante — errado
        por um fator de 14, justamente no caso perigoso.
        """
        import inspect as _inspect

        from app.core import security

        doc = _inspect.getdoc(security._is_token_revoked) or ""
        assert "24h" not in doc or "estava errado" in doc
        assert "14" in doc and "REFRESH" in doc
        assert security.REFRESH_TOKEN_EXPIRE_DAYS == 14


# ── 3. Formato do user_id ──────────────────────────────────────────────────

class TestValidacaoDeUserId:

    @pytest.fixture
    def em_producao(self):
        from app.core.config import settings

        original = settings.APP_ENV
        settings.APP_ENV = "production"
        yield
        settings.APP_ENV = original

    def test_producao_exige_uuid_v4(self, em_producao):
        from fastapi import HTTPException

        from app.core.security import validate_user_id

        valido = str(uuid.uuid4())
        assert validate_user_id(valido) == valido
        for ruim in ("u1", "demo-ana", "golden_user_777", "../etc/passwd"):
            with pytest.raises(HTTPException) as e:
                validate_user_id(ruim)
            assert e.value.status_code == 422

    def test_fora_de_producao_aceita_id_simples(self):
        from app.core.security import validate_user_id

        assert validate_user_id("demo-ana") == "demo-ana"

    def test_nunca_aceita_o_que_nao_e_identificador(self):
        from fastapi import HTTPException

        from app.core.security import validate_user_id

        for ruim in ("a/b", "a b", "'; DROP TABLE users;--", "", "x" * 200):
            with pytest.raises(HTTPException):
                validate_user_id(ruim)


# ── 4. O router sem autenticação não existe mais ───────────────────────────

def _rotas_reais(app) -> list:
    """
    Todas as APIRoute alcançáveis, descendo nos wrappers de inclusão preguiçosa.

    `app.routes` traz `_IncludedRouter`, não as rotas. A primeira versão deste
    teste iterava `app.routes` direto, inspecionava TRÊS rotas — todas na
    allowlist de públicas — e portanto não afirmava nada. Vazio e verde.
    """
    vistos, fila, saida = set(), list(app.routes), []
    while fila:
        rota = fila.pop()
        if id(rota) in vistos:
            continue
        vistos.add(id(rota))
        if getattr(rota, "dependant", None) is not None and getattr(rota, "path", None):
            saida.append(rota)
        original = getattr(rota, "original_router", None)
        if original is not None:
            fila.extend(getattr(original, "routes", []))
        aninhadas = getattr(rota, "routes", None)
        if isinstance(aninhadas, list):
            fila.extend(aninhadas)
    return saida


_DEPS_DE_AUTH = (
    "get_current_user", "require_owner", "require_plan",
    "get_current_token_data", "oauth2_scheme",
    # GET /widget/margem: token de widget (escopo só-leitura, hash no banco,
    # revogável) — o widget de tela inicial não pode usar o refresh rotativo
    "dono_do_token_de_widget",
)


def _tem_auth(rota) -> bool:
    """Procura dependência de autenticação em toda a árvore da rota."""
    pilha, vistos = [rota.dependant], set()
    while pilha:
        dep = pilha.pop()
        if id(dep) in vistos:
            continue
        vistos.add(id(dep))
        if getattr(dep.call, "__name__", "") in _DEPS_DE_AUTH:
            return True
        if any(a in str(getattr(dep, "security_requirements", [])) for a in _DEPS_DE_AUTH):
            return True
        pilha.extend(dep.dependencies)
    return False


# Rotas públicas POR DESENHO. Cada uma com o motivo — a lista é a fronteira
# entre "não precisa de token" e "esqueceram o token".
_PUBLICAS: dict[str, str] = {
    "/health": "liveness", "/readiness": "readiness", "/version": "versão",
    "/openapi.json": "spec", "/docs": "swagger",
    "/docs/oauth2-redirect": "swagger", "/redoc": "redoc",
    "/architect/health": "health do módulo", "/optimizer/health": "health do módulo",
    "/alerts": "health do módulo", "/forecast": "health do módulo",
    "/shadow_invoice": "health do módulo", "/reconnect": "health do módulo",
    "/auth/token": "login", "/auth/register": "cadastro",
    "/auth/refresh": "troca de refresh (valida o próprio token)",
    "/auth/forgot-password": "fluxo de senha esquecida",
    "/auth/reset-password": "consome token de conta",
    "/auth/verify-email": "consome token de conta",
    "/auth/resend-verification": "fluxo de verificação",
    "/auth/check-email": "passo 1 do cadastro, antes de existir conta — limitado a 20/min",
    "/webhook": "webhook Pluggy — autenticado por assinatura HMAC",
    "/transactions/webhook": "webhook Pluggy — assinatura HMAC",
    "/billing/webhook": "webhook Stripe — assinatura + anti-replay",
    "/billing/plans": "catálogo público de planos",
    "/opportunities/products": "catálogo público de produtos",
    "/optimizer/cards": "catálogo público de cartões",
    "/optimizer/promotions": "catálogo público de promoções",
    "/optimizer/promotions/opportunities": "catálogo público",
    "/push/vapid-public-key": "chave PÚBLICA de push",
}


class TestRouterDeRetencao:

    def test_o_modulo_foi_removido(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("app.retention.router")


class TestNenhumaRotaSemAutenticacao:

    @pytest.fixture(scope="class")
    def rotas(self):
        from app.main import app

        return _rotas_reais(app)

    def test_a_varredura_alcanca_a_api_inteira(self, rotas):
        """
        Anti-vacuidade: sem descer nos wrappers, a varredura via 3 rotas e
        passava sem verificar nada.
        """
        assert len(rotas) > 100, f"varredura alcançou só {len(rotas)} rotas"
        assert sum(1 for r in rotas if "user_id" in r.path) > 40

    def test_toda_rota_privada_exige_autenticacao(self, rotas):
        sem_auth = sorted(
            f"{sorted(r.methods)} {r.path}"
            for r in rotas
            if r.path not in _PUBLICAS and not _tem_auth(r)
        )
        assert not sem_auth, f"rotas sem dependência de autenticação: {sem_auth}"

    def test_a_allowlist_nao_tem_entrada_morta(self, rotas):
        """Entrada que não corresponde a rota nenhuma esconde a próxima."""
        caminhos = {r.path for r in rotas} | {
            "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
        }
        mortas = sorted(set(_PUBLICAS) - caminhos)
        assert not mortas, f"entradas públicas sem rota correspondente: {mortas}"


class TestIDORNaSuperficieInteira:
    """
    A afirmação central da doc de segurança, medida em toda a superfície: o
    token de um usuário não alcança os dados de outro.
    """

    @pytest.fixture(scope="class")
    def cliente(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_nenhuma_rota_com_user_id_entrega_dado_alheio(self, cliente):
        from app.core.security import create_access_token

        cabecalho = {"Authorization": f"Bearer {create_access_token({'sub': 'dono-do-token'})}"}
        spec = cliente.get("/openapi.json").json()

        vazaram, testadas = [], 0
        for caminho, operacoes in spec["paths"].items():
            if "{user_id}" not in caminho or "get" not in operacoes:
                continue
            url = caminho.replace("{user_id}", "vitima-alheia")
            if "{" in url:            # sub-recurso exige id extra
                continue
            testadas += 1
            resposta = cliente.get(url, headers=cabecalho)
            if resposta.status_code not in (401, 403, 422):
                vazaram.append(f"{resposta.status_code} {url}")

        assert testadas >= 40, f"só {testadas} rotas testadas — sonda degenerou"
        assert not vazaram, f"acesso cruzado permitido em: {vazaram}"


# ── 5. O baseline de CVE não pode ter ignore obsoleto ──────────────────────

class TestBaselineDeVulnerabilidades:

    @staticmethod
    def _ignores() -> list[str]:
        ci = (_RAIZ.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        return re.findall(r"--ignore-vuln\s+((?:PYSEC|CVE)-[0-9-]+)", ci)

    def test_o_baseline_esta_declarado(self):
        assert len(self._ignores()) >= 5

    def test_sem_ignore_repetido(self):
        ignores = self._ignores()
        assert len(ignores) == len(set(ignores)), "ignore duplicado no CI"

    def test_o_motivo_do_baseline_esta_escrito(self):
        """
        Um `--ignore-vuln` sem racional escrito vira dívida invisível. O
        comentário tem de dizer POR QUE e QUANDO some.
        """
        ci = (_RAIZ.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "BASELINE ACEITO" in ci
        assert "1.x" in ci, "falta dizer que o fix exige a migração para 1.x"
        assert "esvaziada" in ci, "falta dizer quando a lista deve sumir"
