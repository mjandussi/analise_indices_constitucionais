"""Configuração compartilhada pela aplicação de educação.

Este módulo contém somente constantes. Importá-lo não abre sessão, não lê
credenciais e não executa código do Streamlit.
"""

from __future__ import annotations

from decimal import Decimal

from indices_constitucionais.flexvision import CONSULTA_PARTE1, CONSULTA_PARTE2
from indices_constitucionais.modelos import ROTULOS_ESTAGIOS


CONSULTA_RECEITAS = CONSULTA_PARTE1
CONSULTA_DESPESAS = CONSULTA_PARTE2

# Alterar a versão invalida snapshots antigos guardados na sessão Streamlit.
VERSAO_CALCULO = "app-edu-v4-084835-084837-fundeb-fallback"

META_CONSTITUCIONAL = Decimal("25")
REAJUSTE_TOTAL_2026 = Decimal("0.1156")

ESTAGIOS = dict(ROTULOS_ESTAGIOS)
ESTAGIOS_COMPARACAO = (
    "despesa_empenhada",
    "despesa_liquidada",
    "despesa_paga",
)
