"""Núcleo financeiro portátil do índice constitucional de educação."""

from .calculos import calcular_indice_educacao, calcular_parte1, calcular_parte2
from .erros import (
    ErroDadosFlexvision,
    ErroRegraNegocio,
    ErroSchemaFlexvision,
)
from .modelos import (
    ESTAGIOS_DESPESA,
    ROTULOS_ESTAGIOS,
    ResultadoEducacao,
    ResultadoParte1,
    ResultadoParte2,
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
    "ESTAGIOS_DESPESA",
    "HISTORICO_OFICIAL_INDICE",
    "META_CONSTITUCIONAL",
    "MESES_VALIDOS",
    "NOMES_MESES",
    "ROTULOS_ESTAGIOS",
    "TOTAL_MESES_ANO",
    "ErroDadosFlexvision",
    "ErroRegraNegocio",
    "ErroSchemaFlexvision",
    "ResultadoEducacao",
    "ResultadoParte1",
    "ResultadoParte2",
    "calcular_indice_educacao",
    "calcular_monitor_meta",
    "calcular_parte1",
    "calcular_parte2",
    "formatar_brl",
    "formatar_percentual",
    "numero_decimal",
]
