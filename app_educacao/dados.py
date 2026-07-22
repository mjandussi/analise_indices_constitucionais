"""ETL dos CSVs extraídos do Flexvision para os dados usados pela página.

As fórmulas financeiras permanecem em :mod:`indices_constitucionais`, que é a
fonte canônica do projeto. ``processar_snapshot()`` lê `parte1.csv` e
`parte2.csv`; as funções de cálculo isoladas permanecem públicas apenas para
testes e compatibilidade com scripts anteriores.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from indices_constitucionais.educacao import (
    calcular_parte1 as _calcular_parte1,
    calcular_parte2 as _calcular_parte2,
)
from indices_constitucionais.erros import ErroDadosFlexvision
from indices_constitucionais.normalizacao import (
    CENTAVO,
    ZERO,
    formatar_brl,
    formatar_percentual,
    normalizar_texto,
    numero_decimal,
    quantizar_minimo_constitucional,
    quantizar_moeda,
)

from app_educacao.config import ESTAGIOS, ESTAGIOS_COMPARACAO, META_CONSTITUCIONAL


# Nomes mantidos para compatibilidade com quem importava funções do app_edu.py.
ErroDadosEducacao = ErroDadosFlexvision
para_decimal = numero_decimal
moeda = quantizar_moeda


def minimo_25_por_cento(base: Decimal) -> Decimal:
    """Calcula o mínimo monetário sem arredondar para menos de 25%."""

    return quantizar_minimo_constitucional(base * Decimal("0.25"))


def percentual(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    """Calcula um percentual; denominador zero produz valor indisponível."""

    return numerador * Decimal("100") / denominador if denominador else None


def ler_csv(caminho: str | Path) -> list[dict[str, str]]:
    """Lê um CSV da extração preservando todas as células como texto."""

    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {arquivo}.")
    with arquivo.open(encoding="utf-8-sig", newline="") as entrada:
        return list(csv.DictReader(entrada, delimiter=";"))


def processar_snapshot(pasta_snapshot: str | Path) -> dict[str, Any]:
    """Executa a ETL dos dois CSVs publicados por :mod:`extracao`."""

    pasta = Path(pasta_snapshot).expanduser().resolve()
    parte1_csv = pasta / "parte1.csv"
    parte2_csv = pasta / "parte2.csv"
    parte1 = calcular_parte1(ler_csv(parte1_csv))
    parte2 = calcular_parte2(ler_csv(parte2_csv))
    return {
        "parte1": parte1,
        "parte2": parte2,
        "pasta_snapshot": pasta,
    }


def processar_ultimo_snapshot(
    exercicio: int,
    periodo: int,
    *,
    pasta_dados: str | Path | None = None,
) -> dict[str, Any]:
    """Localiza o CSV mais recente do período e executa a ETL."""

    from app_educacao.extracao import PASTA_DADOS_EXTRAIDOS, localizar_snapshot

    pasta_raiz = PASTA_DADOS_EXTRAIDOS if pasta_dados is None else pasta_dados
    pasta_snapshot = localizar_snapshot(
        exercicio,
        periodo,
        pasta_saida=pasta_raiz,
    )
    return processar_snapshot(pasta_snapshot)


def calcular_parte1(payload: Any) -> dict[str, Any]:
    """Normaliza e calcula a Parte 1 por meio da biblioteca canônica."""

    resultado = _calcular_parte1(payload)
    return {
        "componentes": [dict(item) for item in resultado.componentes],
        "base_prevista": resultado.base_prevista,
        "base_arrecadada": resultado.base_arrecadada,
        "diferenca": resultado.diferenca_receita,
        "realizacao_percentual": resultado.realizacao_percentual,
        "minimo_previsto": resultado.minimo_sobre_prevista,
        "minimo_arrecadado": resultado.minimo_sobre_arrecadada,
        "fundeb_previsto": resultado.fundeb_previsto,
        "fundeb_realizado": resultado.fundeb_realizado,
        "avisos": list(resultado.avisos),
    }


def calcular_parte2(payload: Any) -> dict[str, Any]:
    """Normaliza e calcula a Parte 2 por meio da biblioteca canônica."""

    resultado = _calcular_parte2(payload)
    if resultado.total_fundeb is None:
        raise ErroDadosEducacao("O total transferido ao FUNDEB não foi calculado.")
    return {
        "linhas_brutas": [
            _linha_publica_para_interna(indice, item)
            for indice, item in enumerate(resultado.linhas_normalizadas)
        ],
        "linhas_positivas": [
            _copiar_linha(item) for item in resultado.linhas_positivas
        ],
        "total_fundeb": _copiar_linha(resultado.total_fundeb),
        "origem_total_fundeb": resultado.origem_total_fundeb,
        "valores_positivos": dict(resultado.valores_positivos),
        "redutor_a": dict(resultado.redutor_a),
        "redutor_b": dict(resultado.redutor_b),
        "redutor_c": dict(resultado.redutor_c),
        "redutor_d": dict(resultado.redutor_d),
        "outras_linhas": [_copiar_linha(item) for item in resultado.outras_linhas],
        "outras_deducoes": dict(resultado.outras_deducoes),
        "total_aplicado": dict(resultado.total_aplicado),
        "detalhes_a": [_copiar_detalhe(item) for item in resultado.detalhes_a],
        "detalhes_b": _copiar_detalhe(resultado.detalhes_b),
        "detalhes_c": [_copiar_detalhe(item) for item in resultado.detalhes_c],
        "detalhes_d": [_copiar_detalhe(item) for item in resultado.detalhes_d],
    }


def calcular_metricas(
    parte1: Mapping[str, Any], parte2: Mapping[str, Any], estagio: str
) -> dict[str, Any]:
    """Monta as métricas oficiais do período e a visão gerencial anual."""

    if estagio not in ESTAGIOS:
        raise ErroDadosEducacao(f"Estágio inválido: {estagio}.")

    aplicado = parte2["total_aplicado"][estagio]
    base_arrecadada = parte1["base_arrecadada"]
    minimo_periodo = parte1["minimo_arrecadado"]
    indice_periodo = percentual(aplicado, base_arrecadada)
    margem_pp = (
        indice_periodo - META_CONSTITUCIONAL
        if indice_periodo is not None
        else None
    )
    saldo_periodo = moeda(aplicado - minimo_periodo)

    liquidado = parte2["total_aplicado"]["despesa_liquidada"]
    base_prevista = parte1["base_prevista"]
    minimo_anual = parte1["minimo_previsto"]
    indice_anual = percentual(liquidado, base_prevista)
    execucao_meta_anual = percentual(liquidado, minimo_anual)
    saldo_anual = moeda(liquidado - minimo_anual)

    return {
        "estagio": estagio,
        "aplicado": aplicado,
        "base_arrecadada": base_arrecadada,
        "minimo_periodo": minimo_periodo,
        "indice_periodo": indice_periodo,
        "margem_pp": margem_pp,
        "saldo_periodo": saldo_periodo,
        "deficit_periodo": max(-saldo_periodo, ZERO),
        "excedente_periodo": max(saldo_periodo, ZERO),
        "cobertura_minimo": percentual(aplicado, minimo_periodo),
        "atingiu_minimo": (
            indice_periodo is not None
            and indice_periodo >= META_CONSTITUCIONAL
        ),
        "liquidado": liquidado,
        "base_prevista": base_prevista,
        "minimo_anual": minimo_anual,
        "indice_anual": indice_anual,
        "execucao_meta_anual": execucao_meta_anual,
        "saldo_anual": saldo_anual,
        "deficit_anual": max(-saldo_anual, ZERO),
        "excedente_anual": max(saldo_anual, ZERO),
    }


def calcular_todos_os_indices(
    parte1: Mapping[str, Any], parte2: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Calcula os três estágios exibidos no gráfico comparativo."""

    linhas: list[dict[str, Any]] = []
    for estagio in ESTAGIOS_COMPARACAO:
        metricas = calcular_metricas(parte1, parte2, estagio)
        linhas.append(
            {
                "estagio": estagio,
                "rotulo": ESTAGIOS[estagio],
                "indice": metricas["indice_periodo"],
                "aplicado": metricas["aplicado"],
                "atingiu": metricas["atingiu_minimo"],
            }
        )
    return linhas


def _copiar_linha(linha: Mapping[str, Any]) -> dict[str, Any]:
    """Copia uma linha financeira sem compartilhar dicionários mutáveis."""

    return {
        **{chave: valor for chave, valor in linha.items() if chave != "valores"},
        "valores": dict(linha["valores"]),
    }


def _linha_publica_para_interna(
    indice: int, linha: Mapping[str, Any]
) -> dict[str, Any]:
    descricao = str(linha.get("descricao", ""))
    return {
        "indice": indice,
        "descricao": descricao,
        "chave": normalizar_texto(descricao),
        "valores": {estagio: linha[estagio] for estagio in ESTAGIOS},
    }


def _copiar_detalhe(valor: Any) -> Any:
    """Copia recursivamente os pequenos mapas usados nas memórias de cálculo."""

    if isinstance(valor, Mapping):
        return {chave: _copiar_detalhe(item) for chave, item in valor.items()}
    if isinstance(valor, tuple):
        return [_copiar_detalhe(item) for item in valor]
    if isinstance(valor, list):
        return [_copiar_detalhe(item) for item in valor]
    return valor


def main(argv: list[str] | None = None) -> int:
    """CLI curta para conferir os cálculos de um snapshot já extraído."""

    parser = argparse.ArgumentParser(
        description="Processa os CSVs de educação e mostra as métricas principais."
    )
    parser.add_argument("pasta_snapshot", type=Path)
    parser.add_argument(
        "--estagio",
        choices=tuple(ESTAGIOS),
        default="despesa_liquidada",
    )
    argumentos = parser.parse_args(argv)
    resultado = processar_snapshot(argumentos.pasta_snapshot)
    metricas = calcular_metricas(
        resultado["parte1"],
        resultado["parte2"],
        argumentos.estagio,
    )
    print(f"Índice: {formatar_percentual(metricas['indice_periodo'])}")
    print(f"Aplicação: {formatar_brl(metricas['aplicado'])}")
    print(f"Mínimo: {formatar_brl(metricas['minimo_periodo'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
