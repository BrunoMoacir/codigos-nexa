"""
app/pluggy_sync — Sincronização assíncrona com a Pluggy (job + long-polling + SSE).

Por que existe: a Pluggy é assíncrona por natureza. Ao conectar um banco o
item nasce em UPDATING e só fica UPDATED quando a instituição devolve os
dados (de segundos a alguns minutos, com MFA no meio). O POST /pluggy/sync
antigo fazia tudo dentro do request — o cliente ficava pendurado até o proxy
cortar em ~30-60s e a ETL continuava rodando sem ninguém para receber o
resultado.

Aqui o sync vira um job persistido (`pluggy_sync_jobs`) executado em thread,
e o cliente acompanha por:
  - long-polling  GET /pluggy/sync/jobs/{id}?cursor=N   (uma resposta por mudança)
  - streaming     GET /pluggy/sync/jobs/{id}/stream     (SSE, text/event-stream)

O webhook da Pluggy (POST /pluggy/webhook) acorda quem estiver esperando, de
modo que o progresso aparece no instante em que o banco responde e não no
próximo tick do poller.
"""

from app.pluggy_sync.models_orm import PluggySyncJob  # noqa: F401

__all__ = ["PluggySyncJob"]
