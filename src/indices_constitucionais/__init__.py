"""Cálculos de índices constitucionais a partir de consultas Flexvision."""

from .educacao import (
    calcular_indice_educacao,
    calcular_parte1,
    calcular_parte2,
)
from .erros import (
    ErroConsultaFlexvision,
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
from .flexvision import consultar_dados_educacao, consultar_e_calcular_educacao

__all__ = [
    "ESTAGIOS_DESPESA",
    "ROTULOS_ESTAGIOS",
    "ErroConsultaFlexvision",
    "ErroDadosFlexvision",
    "ErroRegraNegocio",
    "ErroSchemaFlexvision",
    "ResultadoEducacao",
    "ResultadoParte1",
    "ResultadoParte2",
    "calcular_indice_educacao",
    "calcular_parte1",
    "calcular_parte2",
    "consultar_dados_educacao",
    "consultar_e_calcular_educacao",
    "formatar_brl",
    "formatar_percentual",
    "numero_decimal",
]
