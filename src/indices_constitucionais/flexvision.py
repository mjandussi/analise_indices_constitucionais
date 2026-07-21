"""Integração fina com o client Flexvision já existente no projeto."""

from __future__ import annotations

import time
from typing import Any

from .educacao import calcular_indice_educacao
from .erros import ErroConsultaFlexvision
from .modelos import ResultadoEducacao


CONSULTA_PARTE1 = "084835"
CONSULTA_PARTE2 = "084837"
STATUS_HTTP_TRANSITORIOS = frozenset({500, 502, 503, 504})


def consultar_dados_educacao(
    api: Any,
    exercicio: int,
    periodo: int,
    *,
    consulta_parte1: str = CONSULTA_PARTE1,
    consulta_parte2: str = CONSULTA_PARTE2,
    timeout: int = 300,
    tentativas_por_consulta: int = 3,
    espera_inicial: float = 1.0,
) -> dict[str, Any]:
    """Busca as duas consultas, usando o mesmo ano/período e a mesma sessão."""

    if tentativas_por_consulta < 1:
        raise ValueError("tentativas_por_consulta deve ser maior ou igual a 1.")
    if espera_inicial < 0:
        raise ValueError("espera_inicial não pode ser negativa.")

    parametros = [int(exercicio), int(periodo)]
    return {
        "parte1": _consultar_com_retentativa(
            api,
            consulta_parte1,
            parametros,
            timeout,
            tentativas_por_consulta,
            espera_inicial,
        ),
        "parte2": _consultar_com_retentativa(
            api,
            consulta_parte2,
            parametros,
            timeout,
            tentativas_por_consulta,
            espera_inicial,
        ),
    }


def consultar_e_calcular_educacao(
    api: Any,
    exercicio: int,
    periodo: int,
    *,
    estagio_indice: str = "despesa_liquidada",
    consulta_parte1: str = CONSULTA_PARTE1,
    consulta_parte2: str = CONSULTA_PARTE2,
    timeout: int = 300,
    tentativas_por_consulta: int = 3,
    espera_inicial: float = 1.0,
) -> ResultadoEducacao:
    """Atalho da extração até as métricas que serão exibidas no Streamlit."""

    dados = consultar_dados_educacao(
        api,
        exercicio,
        periodo,
        consulta_parte1=consulta_parte1,
        consulta_parte2=consulta_parte2,
        timeout=timeout,
        tentativas_por_consulta=tentativas_por_consulta,
        espera_inicial=espera_inicial,
    )
    return calcular_indice_educacao(
        dados["parte1"],
        dados["parte2"],
        estagio_indice=estagio_indice,
    )


def _consultar_com_retentativa(
    api: Any,
    consulta_id: str,
    parametros: list[int],
    timeout: int,
    tentativas: int,
    espera_inicial: float,
) -> Any:
    for tentativa in range(1, tentativas + 1):
        try:
            return api.flexvision.consultar(
                consulta_id,
                parametros=parametros,
                timeout=timeout,
            )
        except Exception as erro:
            resposta = getattr(erro, "response", None)
            if resposta is None:
                raise
            status = getattr(resposta, "status_code", None)
            deve_repetir = (
                status in STATUS_HTTP_TRANSITORIOS and tentativa < tentativas
            )
            if deve_repetir:
                atraso = espera_inicial * (2 ** (tentativa - 1))
                if atraso:
                    time.sleep(atraso)
                continue
            raise ErroConsultaFlexvision(
                consulta_id,
                erro,
                tentativa,
            ) from erro

    raise AssertionError("Fluxo de retentativa terminou sem retorno ou exceção.")
