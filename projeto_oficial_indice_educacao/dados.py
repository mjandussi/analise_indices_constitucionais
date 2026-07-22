"""ETL dos CSVs gerados pela extração do Flexvision.

Este é o único módulo que liga os arquivos ``parte1.csv`` e ``parte2.csv``
às regras financeiras. Os dashboards recebem somente os dicionários devolvidos
por :func:`processar_csvs`.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from config import ESTAGIOS, ESTAGIOS_COMPARACAO, META_CONSTITUCIONAL
from regras.calculos import calcular_parte1, calcular_parte2
from regras.erros import ErroDadosFlexvision
from regras.normalizacao import (
    ZERO,
    formatar_brl,
    formatar_percentual,
    normalizar_texto,
    numero_decimal,
    quantizar_moeda,
)


def ler_csv(caminho: str | Path) -> pd.DataFrame:
    """Lê o CSV como uma planilha, preservando inicialmente os textos."""

    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {arquivo}")

    return pd.read_csv(
        arquivo,
        sep=";",
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )


def preparar_parte1(tabela: pd.DataFrame) -> pd.DataFrame:
    """Dá nomes curtos às colunas da consulta 084835."""

    renomear = {tabela.columns[0]: "descricao"}
    aliases = {
        "RECEITA PREVISTA": "prevista",
        "RECEITA ARRECADADA": "arrecadada",
        "DIFERENCA (B-A)": "diferenca",
        "ARRECADADA/PREVISTA": "percentual",
    }
    for coluna in tabela.columns[1:]:
        nome = normalizar_texto(coluna)
        for trecho, destino in aliases.items():
            if trecho in nome:
                renomear[coluna] = destino
                break

    tabela = tabela.rename(columns=renomear)
    colunas = ("descricao", "prevista", "arrecadada", "diferenca", "percentual")
    _exigir_colunas(tabela, colunas, "Parte 1")
    tabela = tabela[list(colunas)].copy()
    tabela["descricao"] = tabela["descricao"].astype(str).str.strip()
    tabela = tabela[tabela["descricao"] != ""].reset_index(drop=True)
    tabela["chave"] = tabela["descricao"].map(normalizar_texto)
    for coluna in colunas[1:]:
        tabela[coluna] = tabela[coluna].map(numero_decimal)
    return tabela


def preparar_parte2(tabela: pd.DataFrame) -> pd.DataFrame:
    """Dá nomes curtos às colunas da consulta 084837."""

    renomear = {tabela.columns[0]: "descricao"}
    nomes_estagios = {
        normalizar_texto(rotulo): chave for chave, rotulo in ESTAGIOS.items()
    }
    for coluna in tabela.columns[1:]:
        estagio = nomes_estagios.get(normalizar_texto(coluna))
        if estagio:
            renomear[coluna] = estagio

    tabela = tabela.rename(columns=renomear)
    colunas = ("descricao", *ESTAGIOS)
    _exigir_colunas(tabela, colunas, "Parte 2")
    tabela = tabela[list(colunas)].copy()
    tabela["descricao"] = tabela["descricao"].astype(str).str.strip()
    tabela = tabela[tabela["descricao"] != ""].reset_index(drop=True)
    tabela["chave"] = tabela["descricao"].map(normalizar_texto)
    for coluna in ESTAGIOS:
        tabela[coluna] = tabela[coluna].map(numero_decimal)
    return tabela


def processar_csvs(pasta_dados: str | Path) -> dict[str, Any]:
    """Calcula o índice usando exclusivamente parte1.csv e parte2.csv."""

    pasta = Path(pasta_dados).expanduser().resolve()
    parte1 = calcular_parte1(preparar_parte1(ler_csv(pasta / "parte1.csv")))
    parte2 = calcular_parte2(preparar_parte2(ler_csv(pasta / "parte2.csv")))
    return {"parte1": parte1, "parte2": parte2, "pasta_dados": pasta}


def processar_dados_periodo(
    exercicio: int,
    periodo: int,
    *,
    pasta_dados: str | Path | None = None,
) -> dict[str, Any]:
    """Localiza o par de CSVs do período e executa a ETL."""

    from extracao import PASTA_DADOS_EXTRAIDOS, localizar_dados_educacao

    raiz = PASTA_DADOS_EXTRAIDOS if pasta_dados is None else pasta_dados
    return processar_csvs(
        localizar_dados_educacao(exercicio, periodo, pasta_saida=raiz)
    )


def calcular_metricas(
    parte1: Mapping[str, Any],
    parte2: Mapping[str, Any],
    estagio: str,
) -> dict[str, Any]:
    """Calcula as métricas exibidas no dashboard para um estágio da despesa."""

    if estagio not in ESTAGIOS:
        raise ErroDadosFlexvision(f"Estágio inválido: {estagio}")

    aplicado = parte2["total_aplicado"][estagio]
    base = parte1["base_arrecadada"]
    minimo = parte1["minimo_arrecadado"]
    indice = _percentual(aplicado, base)
    saldo = quantizar_moeda(aplicado - minimo)

    # Acompanhamento anual: usa somente valores já realizados. Não projeta
    # despesas futuras; compara a liquidação acumulada com a receita prevista.
    liquidado = parte2["total_aplicado"]["despesa_liquidada"]
    base_prevista = parte1["base_prevista"]
    minimo_anual = parte1["minimo_previsto"]
    indice_anual = _percentual(liquidado, base_prevista)
    execucao_meta_anual = _percentual(liquidado, minimo_anual)

    return {
        "estagio": estagio,
        "aplicado": aplicado,
        "base_arrecadada": base,
        "minimo_periodo": minimo,
        "indice_periodo": indice,
        "margem_pp": indice - META_CONSTITUCIONAL if indice is not None else None,
        "saldo_periodo": saldo,
        "deficit_periodo": max(-saldo, ZERO),
        "excedente_periodo": max(saldo, ZERO),
        "atingiu_minimo": indice is not None and indice >= META_CONSTITUCIONAL,
        "liquidado": liquidado,
        "base_prevista": base_prevista,
        "minimo_anual": minimo_anual,
        "indice_anual": indice_anual,
        "execucao_meta_anual": execucao_meta_anual,
    }


def calcular_todos_os_indices(
    parte1: Mapping[str, Any],
    parte2: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compara os índices empenhado, liquidado e pago."""

    comparacao: list[dict[str, Any]] = []
    for estagio in ESTAGIOS_COMPARACAO:
        metricas = calcular_metricas(parte1, parte2, estagio)
        comparacao.append(
            {
                "Estágio": ESTAGIOS[estagio],
                "Índice (%)": metricas["indice_periodo"],
                "Aplicação": metricas["aplicado"],
                "Atingiu 25%": metricas["atingiu_minimo"],
            }
        )
    return comparacao


def _percentual(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    return numerador * Decimal("100") / denominador if denominador else None


def _exigir_colunas(
    tabela: pd.DataFrame, colunas: tuple[str, ...], parte: str
) -> None:
    ausentes = [coluna for coluna in colunas if coluna not in tabela.columns]
    if ausentes:
        raise ErroDadosFlexvision(
            f"Colunas ausentes na {parte}: {', '.join(ausentes)}."
        )


def main(argv: list[str] | None = None) -> int:
    """Permite validar os dois CSVs pelo terminal, sem abrir o dashboard."""

    parser = argparse.ArgumentParser(description="Calcula os CSVs da Educação.")
    parser.add_argument("pasta_dados", type=Path)
    parser.add_argument(
        "--estagio",
        choices=tuple(ESTAGIOS),
        default="despesa_liquidada",
    )
    argumentos = parser.parse_args(argv)
    resultado = processar_csvs(argumentos.pasta_dados)
    metricas = calcular_metricas(
        resultado["parte1"], resultado["parte2"], argumentos.estagio
    )
    print(f"Índice: {formatar_percentual(metricas['indice_periodo'])}")
    print(f"Aplicação: {formatar_brl(metricas['aplicado'])}")
    print(f"Mínimo: {formatar_brl(metricas['minimo_periodo'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
