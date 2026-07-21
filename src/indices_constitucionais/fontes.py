"""Leitores das exportações CSV usados para conferência offline."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def ler_csv_parte1(caminho: str | Path, *, encoding: str = "latin-1") -> list[dict[str, Any]]:
    """Lê a exportação da Parte 1, descartando os dois cabeçalhos visuais."""

    linhas = _ler_linhas(caminho, encoding)
    if len(linhas) < 4 or len(linhas[2]) < 5:
        raise ValueError("CSV da Parte 1 não possui as três linhas de cabeçalho esperadas.")
    cabecalho = ["descricao", *linhas[2][1:5]]
    return [dict(zip(cabecalho, _completar(linha, len(cabecalho)))) for linha in linhas[3:]]


def ler_csv_parte2(caminho: str | Path, *, encoding: str = "latin-1") -> list[dict[str, Any]]:
    """Lê a exportação tabular da Parte 2."""

    linhas = _ler_linhas(caminho, encoding)
    if len(linhas) < 2:
        raise ValueError("CSV da Parte 2 está vazio ou sem registros.")
    cabecalho = linhas[0]
    return [dict(zip(cabecalho, _completar(linha, len(cabecalho)))) for linha in linhas[1:]]


def _ler_linhas(caminho: str | Path, encoding: str) -> list[list[str]]:
    with Path(caminho).open("r", encoding=encoding, newline="") as arquivo:
        return list(csv.reader(arquivo, delimiter=";"))


def _completar(linha: list[str], tamanho: int) -> list[str]:
    return (linha + [""] * tamanho)[:tamanho]

