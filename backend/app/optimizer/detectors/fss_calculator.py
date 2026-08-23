"""
FSSCalculator — Financial Stress Score (0–100, onde 100 = máximo estresse).

Complementa (não duplica) o resilience_score de profiles.py.
Componentes exclusivos do FSS: rotativo do cartão, cheque especial, queda abrupta de renda.

O FSS é consumido pelo OPP (meses de reserva de emergência protegida), pelo
Bank Match (pesos), pelo optimizer (penalidade de anuidade) e pelo tom do
agente. É um dos poucos números do produto que muda o comportamento de quatro
módulos ao mesmo tempo — por isso ele agora carrega, além do valor, quanta
base ele teve para chegar nele (`fss_confidence`).

O que mudou em 2026-08-23:

1. **Rampas no lugar de degraus.** `income_drop < -0.15 → +20` fazia uma queda
   de 14,9% valer 0 e uma de 15,1% valer 20 pontos — um terço da distância
   entre SAUDAVEL e CRITICO decidido por 0,2 ponto percentual. As rampas
   alcançam o mesmo valor no mesmo ponto de disparo antigo e só adicionam
   sensibilidade ANTES dele: ninguém que era detectado deixa de ser.

2. **Vocabulário de cheque especial de verdade.** Eram quatro strings fixas.
   Faltava `ADIANTAMENTO A DEPOSITANTE` — o termo regulado, que vários bancos
   escrevem literalmente no extrato — e as formas abreviadas que o extrato
   realmente usa. Mesma lição do D3 na Defesa, onde o padrão só aceitava o
   singular e o detector inteiro ficava mudo.

3. **Guarda de cobertura.** `overdraft_months / total_months` com um único mês
   de histórico dava 1/1 = 1,0, ou seja, o sinal MÁXIMO (+25 pontos) a partir
   de uma amostra de um mês. É o mesmo defeito de janela curta já corrigido no
   Radar de Oportunidades, e apontava para o lado perigoso: inflava o estresse
   de quem acabou de conectar a conta.
"""

from __future__ import annotations

import re

import polars as pl

# Cheque especial no extrato brasileiro. `ADIANTAMENTO A DEPOSITANTE` é o
# termo contábil regulado (Res. CMN 4.765/2019 trata do produto por esse nome)
# e aparece literal em vários bancos; `LIS` é o nome comercial do Itaú.
# Compilado UMA vez, com IGNORECASE de verdade — a versão anterior compilava
# com a flag e depois usava `.pattern`, que devolve a string crua e descarta a
# flag. Funcionava por coincidência, porque a coluna era passada por
# `to_uppercase()` antes e o padrão era maiúsculo.
_OVERDRAFT_PATTERN = re.compile(
    r"CHEQUE\s*ESPECIAL"
    r"|LIMITE\s*ESPECIAL"
    r"|ADIANT\w*\s+(A\s+)?DEPOSITANTE"
    r"|USO\s+(DO\s+)?LIMITE"
    r"|UTILIZA\w*\s+(DO\s+)?LIMITE"
    r"|SALDO\s+DEVEDOR"
    r"|\bLIS\b"
    r"|(JUROS|IOF|ENCARGOS?)\s+(DO\s+)?(CHEQUE|LIMITE|ADIANT|LIS|ESPECIA)\w*",
    re.IGNORECASE,
)

# Abaixo disso a fração de meses com cheque especial não é estimável: um único
# mês de dado transformaria uma ocorrência no sinal máximo.
_MIN_MESES_PARA_OVERDRAFT = 2

# Cobertura de dados → confiança no FSS. Não altera o score; diz o quanto
# confiar nele. Três meses é a janela de referência do produto.
_CONFIANCA_POR_MESES = {0: 0.0, 1: 0.3, 2: 0.6}
_CONFIANCA_PLENA = 1.0


def _rampa(valor: float, inicio: float, fim: float, maximo: float) -> float:
    """
    Interpolação linear de 0 (em `inicio`) até `maximo` (em `fim`), saturando
    fora do intervalo. Funciona nos dois sentidos — `fim` pode ser menor que
    `inicio`, para sinais em que "pior" significa "mais negativo".
    """
    if inicio == fim:
        return maximo if valor >= inicio else 0.0
    fracao = (valor - inicio) / (fim - inicio)
    return maximo * max(0.0, min(1.0, fracao))


class FSSCalculator:
    """
    Financial Stress Score — índice 0–100 (100 = máximo estresse).

    Quando resilience_score disponível: usa como base (evita recalcular savings_rate,
    tendência e committed_pct) e adiciona apenas sinais exclusivos do FSS.
    """

    def calc_fss(
        self,
        profile,
        txns_90d: pl.DataFrame,
        income_3m_avg: float | None = None,
        income_12m_avg: float | None = None,
        resilience_score: int | None = None,
    ) -> dict:
        score = 0.0
        signals = []

        if resilience_score is not None:
            base_stress = max(0, (100 - resilience_score) * 0.50)
            score += base_stress
            if resilience_score < 35:
                signals.append(f"low_resilience={resilience_score}")
        else:
            # Rampa contínua: +15 em -5% ou pior, chegando a 0 em +5%.
            # Antes eram dois degraus (+15 abaixo de -5%, +7 abaixo de +5%),
            # e quem poupava 4,9% levava a mesma penalidade de quem poupava 0.
            savings_pct = getattr(profile, "savings_rate", 0.0)
            savings_stress = _rampa(savings_pct, 5.0, -5.0, 15.0)
            if savings_stress > 0:
                score += savings_stress
                if savings_pct < -5:
                    signals.append(f"negative_savings_rate={savings_pct:.1f}%")
                else:
                    signals.append("low_savings_rate")

            future_commitment = profile.committed_percentage
            if future_commitment > 0.4:
                score += min((future_commitment - 0.4) * 100, 20)
                signals.append(f"future_commitment={future_commitment:.1%}")

        # Rotativo do cartão — EXCLUSIVO FSS
        #
        # `credit_spend_ratio > 0.7` era um portão binário: 0,699 zerava o
        # sinal inteiro, 0,701 liberava os 30 pontos. Agora ele modula — a
        # concentração em crédito pesa proporcionalmente, alcançando o peso
        # cheio no mesmo 0,70 de antes.
        peso_credito = _rampa(profile.credit_spend_ratio, 0.5, 0.7, 1.0)
        if profile.committed_percentage > 0.5 and peso_credito > 0:
            revolving_score = min((profile.committed_percentage - 0.5) * 60, 30) * peso_credito
            score += revolving_score
            signals.append(
                f"likely_revolving={profile.committed_percentage:.1%}"
                f"@credit={profile.credit_spend_ratio:.0%}"
            )

        # Cheque especial — EXCLUSIVO FSS
        overdraft_score, meses_cobertos = self._calc_overdraft_usage(txns_90d)
        score += overdraft_score * 25
        if overdraft_score > 0.1:
            signals.append(f"overdraft_usage={overdraft_score:.1%}")

        # Queda abrupta de renda — EXCLUSIVO FSS
        # income_3m_avg pode ser 0.0 (renda caiu para zero = maior sinal de estresse);
        # `if income_3m_avg` bloquearia esse caso, então usa `is not None`.
        if income_3m_avg is not None and income_12m_avg is not None and income_12m_avg > 0:
            income_drop = (income_3m_avg - income_12m_avg) / income_12m_avg
            # Rampa: 0 em -5%, cheia (+20) em -15% — o mesmo ponto em que o
            # degrau antigo disparava — e saturada dali para baixo. Uma queda
            # de 12% deixa de valer zero.
            drop_stress = _rampa(income_drop, -0.05, -0.15, 20.0)
            if drop_stress > 0:
                score += drop_stress
                signals.append(f"income_drop={income_drop:.1%}")

        fss = round(min(score, 100.0), 1)

        if fss <= 20:
            level = "SAUDAVEL"
        elif fss <= 40:
            level = "ATENCAO"
        elif fss <= 65:
            level = "ALERTA"
        else:
            level = "CRITICO"

        confianca = _CONFIANCA_POR_MESES.get(meses_cobertos, _CONFIANCA_PLENA)
        if confianca < _CONFIANCA_PLENA:
            signals.append(f"cobertura_parcial={meses_cobertos}m")

        return {
            "fss": fss,
            "fss_level": level,
            "fss_signals": signals,
            # Quanto do FSS veio de base suficiente. Não altera o score — diz
            # quanto confiar nele. Quem acabou de conectar a conta recebe um
            # número, mas não o mesmo peso de quem tem 3 meses de histórico.
            "fss_confidence": round(confianca, 2),
            "fss_months_covered": meses_cobertos,
        }

    def _calc_overdraft_usage(self, df: pl.DataFrame) -> tuple[float, int]:
        """
        `(fração_de_meses_com_cheque_especial, meses_cobertos)`.

        Com menos de `_MIN_MESES_PARA_OVERDRAFT` meses a fração não é
        estimável e volta 0.0 — um mês de histórico com uma cobrança daria
        1/1 = 1,0, o sinal máximo, a partir de uma amostra de um mês.
        """
        if df.is_empty() or "description" not in df.columns:
            return 0.0, 0

        com_mes = df.with_columns(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        )
        total_months = com_mes.select("ym").unique().height
        if total_months < _MIN_MESES_PARA_OVERDRAFT:
            return 0.0, total_months

        overdraft_months = (
            com_mes.filter(pl.col("description").str.contains(f"(?i){_OVERDRAFT_PATTERN.pattern}"))
            .select("ym")
            .unique()
            .height
        )
        return overdraft_months / total_months, total_months
