"""Regras financeiras do índice constitucional de Educação."""

from .calculos import calcular_parte1, calcular_parte2
from .erros import (
    ErroDadosFlexvision,
    ErroRegraNegocio,
    ErroSchemaFlexvision,
)
from .normalizacao import formatar_brl, formatar_percentual, numero_decimal
from .projecao import (
    HISTORICO_OFICIAL_INDICE,
    META_CONSTITUCIONAL,
    MESES_VALIDOS,
    NOMES_MESES,
    TOTAL_MESES_ANO,
    calcular_monitor_meta,
)

__all__ = [
    "HISTORICO_OFICIAL_INDICE",
    "META_CONSTITUCIONAL",
    "MESES_VALIDOS",
    "NOMES_MESES",
    "TOTAL_MESES_ANO",
    "ErroDadosFlexvision",
    "ErroRegraNegocio",
    "ErroSchemaFlexvision",
    "calcular_monitor_meta",
    "calcular_parte1",
    "calcular_parte2",
    "formatar_brl",
    "formatar_percentual",
    "numero_decimal",
]
