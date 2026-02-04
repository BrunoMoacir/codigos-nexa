"""
app/etl/recurring_detector.py - Detecta Padrões Recorrentes em Transações

╔══════════════════════════════════════════════════════════════════════╗
║ RESPONSABILIDADE                                                     ║
╚══════════════════════════════════════════════════════════════════════╝

Marca transações com flags de recorrência:
    - is_recurring: True se for assinatura (Netflix, Spotify, etc)
    - is_installment: True se for parcelamento (12x, 24x, etc)
    - installment_info: "3/12" (parcela 3 de 12) se parcelamento

╔══════════════════════════════════════════════════════════════════════╗
║ COMO FUNCIONA                                                        ║
╚══════════════════════════════════════════════════════════════════════╝

1. Usa SubscriptionDetector para encontrar assinaturas
2. Usa InstallmentDetector para encontrar parcelamentos
3. Faz JOIN com DataFrame original
4. Adiciona flags: is_recurring, is_installment, installment_info

╔══════════════════════════════════════════════════════════════════════╗
║ INTEGRAÇÃO COM SHADOW INVOICES                                       ║
╚══════════════════════════════════════════════════════════════════════╝

Shadow Invoices:
    - Detecta FUTURAS obrigações
    - Retorna: type, amount, next_due_date, metadata, confidence

RecurringDetector:
    - Marca transações HISTÓRICAS
    - Retorna: DataFrame com flags adicionadas
    - Usa os MESMOS detectores internamente

Diferença:
    - Shadow Invoices → Projeção futura
    - RecurringDetector → Classificação histórica

╔══════════════════════════════════════════════════════════════════════╗
║ USAGE                                                                ║
╚══════════════════════════════════════════════════════════════════════╝

from app.etl import RecurringDetector

detector = RecurringDetector()
df_with_flags = detector.detect(df)

# Verificar flags
subscriptions = df_with_flags.filter(pl.col("is_recurring") == True)
installments = df_with_flags.filter(pl.col("is_installment") == True)
"""

import logging
import polars as pl
from typing import Optional

from app.etl.shadow_invoices.subscription_detector import SubscriptionDetector
from app.etl.shadow_invoices.installment_detector import InstallmentDetector

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RECURRING DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RecurringDetector:
    """
    Detecta e marca padrões recorrentes em transações.
    
    Responsabilidades:
        1. Detecta assinaturas (SubscriptionDetector)
        2. Detecta parcelamentos (InstallmentDetector)
        3. Adiciona flags ao DataFrame original
    
    Flags adicionadas:
        - is_recurring (bool): True se assinatura
        - is_installment (bool): True se parcelamento
        - installment_info (str | None): "3/12" se parcelamento
        - recurring_confidence (float | None): Confiança da detecção
    
    Example:
        >>> detector = RecurringDetector()
        >>> df_flagged = detector.detect(df)
        >>> 
        >>> # Filtrar assinaturas
        >>> subscriptions = df_flagged.filter(pl.col("is_recurring") == True)
        >>> 
        >>> # Filtrar parcelamentos
        >>> installments = df_flagged.filter(pl.col("is_installment") == True)
    """
    
    def __init__(self):
        """Inicializa detectores internos."""
        self.logger = logging.getLogger(__name__)
        
        # Detectores de Shadow Invoice (reutilizados)
        self.subscription_detector = SubscriptionDetector()
        self.installment_detector = InstallmentDetector()
        
        self.logger.info("RecurringDetector inicializado")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta padrões recorrentes e adiciona flags ao DataFrame.
        
        Args:
            df: DataFrame com transações normalizadas
                Colunas obrigatórias:
                - description (str)
                - amount (float)
                - transaction_date (datetime)
        
        Returns:
            DataFrame original + flags:
                - is_recurring (bool)
                - is_installment (bool)
                - installment_info (str | None)
                - recurring_confidence (float | None)
        
        Example:
            >>> df = pl.DataFrame({
            ...     "description": ["netflix", "uber eats", "celular 3/12"],
            ...     "amount": [-39.90, -45.00, -120.00],
            ...     "transaction_date": [...]
            ... })
            >>> df_flagged = detector.detect(df)
            >>> print(df_flagged.select([
            ...     "description", 
            ...     "is_recurring", 
            ...     "is_installment"
            ... ]))
            ┌─────────────┬──────────────┬────────────────┐
            │ description ┆ is_recurring ┆ is_installment │
            ├─────────────┼──────────────┼────────────────┤
            │ netflix     ┆ true         ┆ false          │
            │ uber eats   ┆ false        ┆ false          │
            │ celular 3/12┆ false        ┆ true           │
            └─────────────┴──────────────┴────────────────┘
        """
        # Validação
        if df.is_empty():
            self.logger.warning("DataFrame vazio. Retornando sem flags.")
            return self._add_empty_flags(df)
        
        self._validate_required_columns(df)
        
        self.logger.info(f"Detectando padrões recorrentes em {df.height} transações")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: DETECTAR ASSINATURAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        subscriptions_df = self.subscription_detector.detect(df)
        
        self.logger.debug(
            f"Assinaturas detectadas: {subscriptions_df.height if not subscriptions_df.is_empty() else 0}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: DETECTAR PARCELAMENTOS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        installments_df = self.installment_detector.detect(df)
        
        self.logger.debug(
            f"Parcelamentos detectados: {installments_df.height if not installments_df.is_empty() else 0}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CRIAR FLAGS NO DATAFRAME ORIGINAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df_flagged = self._add_recurring_flags(
            df, 
            subscriptions_df, 
            installments_df
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: EXTRAIR INSTALLMENT_INFO (parcela N/M)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df_flagged = self._extract_installment_info(df_flagged)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LOG RESUMO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        recurring_count = df_flagged.filter(pl.col("is_recurring") == True).height
        installment_count = df_flagged.filter(pl.col("is_installment") == True).height
        
        self.logger.info(
            f"Detecção concluída: "
            f"{recurring_count} assinaturas, "
            f"{installment_count} parcelamentos"
        )
        
        return df_flagged
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _validate_required_columns(self, df: pl.DataFrame):
        """Valida colunas obrigatórias."""
        required = {"description", "amount", "transaction_date"}
        missing = required - set(df.columns)
        
        if missing:
            raise ValueError(
                f"Colunas obrigatórias faltando: {missing}. "
                f"Presentes: {set(df.columns)}"
            )
    
    def _add_empty_flags(self, df: pl.DataFrame) -> pl.DataFrame:
        """Adiciona flags vazias se DataFrame vazio."""
        return df.with_columns([
            pl.lit(False).alias("is_recurring"),
            pl.lit(False).alias("is_installment"),
            pl.lit(None).cast(pl.Utf8).alias("installment_info"),
            pl.lit(None).cast(pl.Float64).alias("recurring_confidence")
        ])
    
    def _add_recurring_flags(
        self,
        df: pl.DataFrame,
        subscriptions_df: pl.DataFrame,
        installments_df: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Adiciona flags baseadas nas detecções.
        
        Lógica:
            1. Extrai descriptions de subscriptions e installments
            2. Marca is_recurring=True se description em subscriptions
            3. Marca is_installment=True se description em installments
            4. Adiciona recurring_confidence (prioriza subscription > installment)
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # EXTRAIR DESCRIPTIONS DETECTADAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Subscriptions
        subscription_descriptions = set()
        subscription_confidence_map = {}
        
        if not subscriptions_df.is_empty():
            for row in subscriptions_df.iter_rows(named=True):
                desc = row["metadata"]["description"]
                conf = row["confidence"]
                subscription_descriptions.add(desc)
                subscription_confidence_map[desc] = conf
        
        # Installments
        installment_descriptions = set()
        installment_confidence_map = {}
        
        if not installments_df.is_empty():
            for row in installments_df.iter_rows(named=True):
                desc = row["metadata"]["description"]
                conf = row["confidence"]
                installment_descriptions.add(desc)
                installment_confidence_map[desc] = conf
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CRIAR FLAGS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        df = df.with_columns([
            # is_recurring
            pl.col("description").is_in(list(subscription_descriptions)).alias("is_recurring"),
            
            # is_installment
            pl.col("description").is_in(list(installment_descriptions)).alias("is_installment"),
        ])
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ADICIONAR CONFIDENCE (prioriza subscription)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Mapa combinado (subscription sobrescreve installment)
        confidence_map = {**installment_confidence_map, **subscription_confidence_map}
        
        # Adicionar coluna recurring_confidence
        df = df.with_columns(
            pl.col("description")
            .map_elements(
                lambda desc: confidence_map.get(desc, None),
                return_dtype=pl.Float64
            )
            .alias("recurring_confidence")
        )
        
        return df
    
    def _extract_installment_info(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Extrai installment_info da description (ex: "3/12", "10x").
        
        Padrões reconhecidos:
            - "3/12" → "3/12"
            - "10x" → "10/10" (assume que é parcela 10 de 10)
            - "parc 3 de 12" → "3/12"
        
        Returns:
            DataFrame com coluna installment_info adicionada
        """
        import re
        
        def parse_installment(desc: str, is_installment: bool) -> Optional[str]:
            """Extrai formato N/M da description."""
            if not is_installment or not desc:
                return None
            
            # Padrão 1: "3/12"
            match = re.search(r"(\d+)/(\d+)", desc)
            if match:
                n, m = match.groups()
                return f"{n}/{m}"
            
            # Padrão 2: "10x"
            match = re.search(r"(\d+)x\b", desc, re.IGNORECASE)
            if match:
                n = match.group(1)
                return f"{n}/{n}"  # Assume última parcela
            
            # Padrão 3: "parc 3 de 12"
            match = re.search(r"parc[a-z]*\s*(\d+)\s*de\s*(\d+)", desc, re.IGNORECASE)
            if match:
                n, m = match.groups()
                return f"{n}/{m}"
            
            return None
        
        # Aplicar parsing
        df = df.with_columns(
            pl.struct(["description", "is_installment"])
            .map_elements(
                lambda row: parse_installment(row["description"], row["is_installment"]),
                return_dtype=pl.Utf8
            )
            .alias("installment_info")
        )
        
        return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTIONS (Public API)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_recurring_patterns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Função helper que encapsula RecurringDetector.detect().
    
    Útil para imports diretos:
        from app.etl.recurring_detector import detect_recurring_patterns
    
    Args:
        df: DataFrame com transações
    
    Returns:
        DataFrame com flags de recorrência
    
    Example:
        >>> df_flagged = detect_recurring_patterns(df)
    """
    detector = RecurringDetector()
    return detector.detect(df)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATS & DEBUG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_recurring_stats(df: pl.DataFrame):
    """
    Exibe estatísticas de recorrência (debug).
    
    Args:
        df: DataFrame com flags (pós-detecção)
    
    Example:
        >>> df_flagged = detector.detect(df)
        >>> print_recurring_stats(df_flagged)
        
        📊 ESTATÍSTICAS DE RECORRÊNCIA:
        ════════════════════════════════════════════════════════════════
        Total de transações: 1000
        
        🔁 ASSINATURAS (is_recurring=True):
            - Quantidade: 45 (4.5%)
            - Valor médio: R$ -39.90
            - Top 3:
                1. netflix (confidence: 0.90)
                2. spotify (confidence: 0.90)
                3. amazon prime (confidence: 0.90)
        
        📦 PARCELAMENTOS (is_installment=True):
            - Quantidade: 120 (12.0%)
            - Valor médio: R$ -150.00
            - Top 3:
                1. celular 3/12 (confidence: 0.90)
                2. geladeira 2/10 (confidence: 0.85)
                3. notebook 5/24 (confidence: 0.70)
        ════════════════════════════════════════════════════════════════
    """
    if "is_recurring" not in df.columns or "is_installment" not in df.columns:
        print("❌ DataFrame não contém flags de recorrência")
        print("   Execute detector.detect(df) primeiro")
        return
    
    total = df.height
    
    # Assinaturas
    subscriptions = df.filter(pl.col("is_recurring") == True)
    sub_count = subscriptions.height
    sub_pct = (sub_count / total * 100) if total > 0 else 0
    sub_avg = float(subscriptions["amount"].mean()) if sub_count > 0 else 0.0
    
    # Parcelamentos
    installments = df.filter(pl.col("is_installment") == True)
    inst_count = installments.height
    inst_pct = (inst_count / total * 100) if total > 0 else 0
    inst_avg = float(installments["amount"].mean()) if inst_count > 0 else 0.0
    
    # Top assinaturas
    top_subs = []
    if sub_count > 0:
        top_subs = (
            subscriptions
            .group_by("description")
            .agg(pl.col("recurring_confidence").first())
            .sort("recurring_confidence", descending=True)
            .head(3)
            .to_dicts()
        )
    
    # Top parcelamentos
    top_insts = []
    if inst_count > 0:
        top_insts = (
            installments
            .group_by("description")
            .agg(pl.col("recurring_confidence").first())
            .sort("recurring_confidence", descending=True)
            .head(3)
            .to_dicts()
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRINT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("\n📊 ESTATÍSTICAS DE RECORRÊNCIA:")
    print("=" * 80)
    print(f"Total de transações: {total}")
    
    # Assinaturas
    print(f"\n🔁 ASSINATURAS (is_recurring=True):")
    print(f"    - Quantidade: {sub_count} ({sub_pct:.1f}%)")
    print(f"    - Valor médio: R$ {sub_avg:.2f}")
    
    if top_subs:
        print(f"    - Top 3:")
        for i, row in enumerate(top_subs, 1):
            conf = row["recurring_confidence"] or 0.0
            print(f"        {i}. {row['description']} (confidence: {conf:.2f})")
    else:
        print(f"    - Nenhuma detectada")
    
    # Parcelamentos
    print(f"\n📦 PARCELAMENTOS (is_installment=True):")
    print(f"    - Quantidade: {inst_count} ({inst_pct:.1f}%)")
    print(f"    - Valor médio: R$ {inst_avg:.2f}")
    
    if top_insts:
        print(f"    - Top 3:")
        for i, row in enumerate(top_insts, 1):
            conf = row["recurring_confidence"] or 0.0
            print(f"        {i}. {row['description']} (confidence: {conf:.2f})")
    else:
        print(f"    - Nenhum detectado")
    
    print("=" * 80)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIM DO ARQUIVO recurring_detector.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
📊 RESUMO DO MÓDULO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLASSES:
    - RecurringDetector: Classe principal
        ✓ detect(df) → DataFrame com flags

FUNÇÕES PÚBLICAS:
    - detect_recurring_patterns(df) → Wrapper simplificado
    - print_recurring_stats(df) → Exibe estatísticas

FLAGS ADICIONADAS AO DATAFRAME:
    - is_recurring (bool): True se assinatura
    - is_installment (bool): True se parcelamento
    - installment_info (str | None): "3/12" se parcelamento
    - recurring_confidence (float | None): Confiança da detecção

INTEGRAÇÃO:
    - Usa SubscriptionDetector (shadow_invoices)
    - Usa InstallmentDetector (shadow_invoices)
    - Compatível com TransactionClassifier
    - Compatível com DataQualityValidator (próximo módulo)

TESTES NECESSÁRIOS:
    1. Testar com DataFrame vazio
    2. Testar com assinaturas (Netflix, Spotify)
    3. Testar com parcelamentos (3/12, 10x)
    4. Testar extração de installment_info
    5. Testar priorização (subscription > installment)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""