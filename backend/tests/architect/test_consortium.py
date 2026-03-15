"""
tests/architect/test_consortium.py - Testes da calculadora de consórcio (Monte Carlo)

ASSINATURA REAL:
    calculate_consortium_metrics(
        letter_value, months, admin_rate,
        reserve_fund_rate=0.0,
        bid_strategy='fixed', bid_amount=0.0,
        num_simulations=2000
    ) -> ConsortiumResult

ConsortiumResult:
    .contemplation_month_expected: int
    .contemplation_probability: Dict[str, float]  # ex: {"6m": 0.1, "12m": 0.3}
    .total_cost: float
    .monthly_payment: float
    .admin_fee_total: float
    .scenarios: int

O QUE É TESTADO:
    - Retorna ConsortiumResult com campos preenchidos
    - contemplation_probability é cumulativa (crescente)
    - total_cost > letter_value (inclui taxa adm)
    - contemplation_month_expected entre 1 e months
    - Custo maior com taxa adm maior

COMO RODAR:
    cd backend
    pytest tests/architect/test_consortium.py -v
"""

import pytest

from app.architect.calculators.consortium import calculate_consortium_metrics, ConsortiumResult

# Parâmetros base
_VALOR = 50_000.0
_MESES = 60
_TAXA_ADM = 0.15    # 15% — típico de consórcio de veículo


class TestCalculateConsortiumMetrics:
    """Testa o simulador de consórcio Monte Carlo."""

    def test_retorna_consortium_result(self):
        """Deve retornar instância de ConsortiumResult."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        assert isinstance(res, ConsortiumResult)

    def test_contemplation_probability_e_dict(self):
        """contemplation_probability deve ser um dict."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        assert isinstance(res.contemplation_probability, dict)

    def test_contemplation_probability_tem_chaves(self):
        """O dict de probabilide deve ter chaves como '12m' ou '6m'."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        # deve ter pelo menos uma chave
        assert len(res.contemplation_probability) > 0

    def test_probabilidades_sao_crescentes(self):
        """
        Probabilidades cumulativas devem ser crescentes.
        Ex: prob['6m'] <= prob['12m'] <= prob['24m'] <= prob['36m']
        """
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        probs = res.contemplation_probability
        # Extrair as chaves que têm formato "Nm" (ignorar 'half_term' e similares)
        numeric_keys = [k for k in probs.keys() if k.replace("m", "").isdigit()]
        keys_sorted = sorted(numeric_keys, key=lambda k: int(k.replace("m", "")))
        if len(keys_sorted) < 2:
            return  # Não há pares suficientes para comparar
        vals = [probs[k] for k in keys_sorted]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1], \
                f"Probabilidade não crescente: {keys_sorted[i]}={vals[i]} > {keys_sorted[i+1]}={vals[i+1]}"

    def test_probabilidades_entre_0_e_1(self):
        """Probabilidades devem estar no intervalo [0, 1]."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        for k, v in res.contemplation_probability.items():
            assert 0.0 <= v <= 1.0, f"Probabilidade fora de [0,1]: {k}={v}"

    def test_custo_total_maior_que_valor_bem(self):
        """Custo total do consórcio deve ser > letter_value (taxa adm embutida)."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        assert res.total_cost > _VALOR

    def test_taxa_zero_custo_proximo_ao_valor(self):
        """Com taxa adm = 0, custo nominal ≈ valor do bem.

        O custo *real* (total_cost_real) será maior devido ao reajuste anual
        da carta (IPCA/INCC). O custo *nominal* (total_cost_nominal) deve
        ser igual ao letter_value quando as taxas são zero.
        """
        res = calculate_consortium_metrics(_VALOR, _MESES, 0.0)
        # Sem taxas, o custo nominal = letter_value (sem reajuste)
        assert abs(res.total_cost_nominal - _VALOR) / _VALOR < 0.01

    def test_maior_taxa_adm_maior_custo(self):
        """Taxa administrativa maior → custo total maior."""
        res_5  = calculate_consortium_metrics(_VALOR, _MESES, 0.05)
        res_25 = calculate_consortium_metrics(_VALOR, _MESES, 0.25)
        assert res_25.total_cost > res_5.total_cost

    def test_contemplation_month_dentro_do_prazo(self):
        """Mês esperado de contemplação deve estar entre 1 e total de meses."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        assert 1 <= res.contemplation_month_expected <= _MESES

    def test_monthly_payment_positivo(self):
        """Parcela mensal deve ser positiva."""
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        assert res.monthly_payment > 0

    def test_scenarios_igual_ao_solicitado(self):
        """Número de cenários simulados deve ser o solicitado."""
        n = 500  # usar poucos para velocidade
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM, num_simulations=n)
        assert res.scenarios == n

    def test_admin_fee_total_proporcional(self):
        """Taxa adm total >= admin_rate * letter_value (reajuste eleva a base).

        Com reajuste anual, a carta cresce ao longo do prazo e as parcelas
        de taxa administrativa são calculadas sobre o valor corrigido.
        Por isso admin_fee_total >= admin_rate * letter_value.
        O valor nominal (sem reajuste) seria exatamente admin_rate * letter_value.
        """
        res = calculate_consortium_metrics(_VALOR, _MESES, _TAXA_ADM)
        expected_fee_nominal = _VALOR * _TAXA_ADM
        # Com reajuste, taxa adm real >= nominal
        assert res.admin_fee_total >= expected_fee_nominal
