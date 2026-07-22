"""Define as duas consultas de educação e chama ``extracao_flex.py``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from config import (
    ARQUIVO_ENV,
    CONSULTA_DESPESAS,
    CONSULTA_RECEITAS,
    PASTA_DADOS_EXTRAIDOS,
)
from extracao_flex import extrair_consultas, ler_credenciais


def extrair_dados_educacao(
    exercicio: int,
    periodo: int,
    pasta_saida: str | Path = PASTA_DADOS_EXTRAIDOS,
    credenciais: tuple[str, str] | None = None,
) -> Path:
    """Executa Flexvision → JSON → CSV para as duas consultas."""

    ano, mes = _validar_referencia(exercicio, periodo)
    usuario, senha = credenciais or ler_credenciais(ARQUIVO_ENV)
    consultas = [
        {
            "nome": "parte1",
            "consulta_id": CONSULTA_RECEITAS,
            "parametros": [ano, mes],
        },
        {
            "nome": "parte2",
            "consulta_id": CONSULTA_DESPESAS,
            "parametros": [ano, mes],
        },
    ]

    pasta = Path(pasta_saida).resolve() / str(ano) / f"{mes:02d}"
    extrair_consultas(consultas, pasta, usuario, senha, ARQUIVO_ENV)
    return pasta


def localizar_dados_educacao(
    exercicio: int,
    periodo: int,
    pasta_saida: str | Path = PASTA_DADOS_EXTRAIDOS,
) -> Path:
    """Localiza os JSONs e CSVs da última extração do período."""

    ano, mes = _validar_referencia(exercicio, periodo)
    pasta = Path(pasta_saida).resolve() / str(ano) / f"{mes:02d}"
    nomes = ("parte1.json", "parte1.csv", "parte2.json", "parte2.csv")
    if not all((pasta / nome).is_file() for nome in nomes):
        raise FileNotFoundError(f"Dados não encontrados para {ano}/{mes:02d}.")
    return pasta


def _validar_referencia(exercicio: int, periodo: int) -> tuple[int, int]:
    ano, mes = int(exercicio), int(periodo)
    if ano < 2000 or mes not in range(1, 13):
        raise ValueError("Informe exercício >= 2000 e período entre 1 e 12.")
    return ano, mes


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extrai 084835 e 084837 e gera os CSVs da Educação."
    )
    parser.add_argument("exercicio", type=int)
    parser.add_argument("periodo", type=int, choices=range(1, 13))
    parser.add_argument("--pasta-saida", type=Path, default=PASTA_DADOS_EXTRAIDOS)
    opcoes = parser.parse_args(argumentos)
    pasta = extrair_dados_educacao(
        opcoes.exercicio,
        opcoes.periodo,
        opcoes.pasta_saida,
    )
    print(pasta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
