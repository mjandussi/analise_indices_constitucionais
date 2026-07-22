"""Extração dos dados de educação, sem regras de negócio ou interface.

A consulta acontece em memória dentro de uma única sessão. Em seguida, o
fluxo completo publica os dois CSVs juntos; esses arquivos são a fronteira
obrigatória entre a extração e a ETL. A função de consulta isolada permanece
disponível para testes e integrações de baixo nível.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from indices_constitucionais.flexvision import (
    CONSULTA_PARTE1,
    CONSULTA_PARTE2,
    consultar_dados_educacao,
)
from indices_constitucionais.normalizacao import extrair_registros


CONSULTA_RECEITAS = CONSULTA_PARTE1
CONSULTA_DESPESAS = CONSULTA_PARTE2
RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_DADOS_EXTRAIDOS = RAIZ_PROJETO / "dados_extraidos"


class ErroConfiguracaoExtracao(RuntimeError):
    """Indica que o ambiente ainda não permite consultar o Flexvision."""


def ler_credenciais(
    arquivo_env: str | Path | None = None,
) -> tuple[str, str]:
    """Lê credenciais do ambiente e completa ausências pelo ``.env`` da raiz.

    Variáveis de ambiente têm precedência. O arquivo só é aberto quando uma
    das duas variáveis não está definida, e seu conteúdo nunca é devolvido em
    mensagens de erro.
    """

    usuario = os.getenv("SIAFE_USUARIO")
    senha = os.getenv("SIAFE_SENHA")

    caminho_env = Path(arquivo_env) if arquivo_env is not None else RAIZ_PROJETO / ".env"
    if (not usuario or not senha) and caminho_env.is_file():
        try:
            from dotenv import dotenv_values
        except ImportError as erro:
            raise ErroConfiguracaoExtracao(
                "O pacote python-dotenv é necessário para ler credenciais do arquivo .env."
            ) from erro

        valores = dotenv_values(caminho_env)
        usuario = usuario or valores.get("SIAFE_USUARIO")
        senha = senha or valores.get("SIAFE_SENHA")

    if not usuario or not senha:
        raise ErroConfiguracaoExtracao(
            "Credenciais ausentes. Defina SIAFE_USUARIO e SIAFE_SENHA "
            "no ambiente ou no arquivo .env da raiz do projeto."
        )
    return str(usuario), str(senha)


def extrair_dados_educacao(
    exercicio: int,
    periodo: int,
    *,
    timeout: int = 300,
    tentativas_por_consulta: int = 3,
    espera_inicial: float = 1.0,
    fabrica_api: Callable[..., Any] | None = None,
    credenciais: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Consulta as Partes 1 e 2 na mesma sessão e retorna os dados em memória.

    ``fabrica_api`` e ``credenciais`` são pontos de substituição para testes e
    integrações controladas. No uso normal, o client é importado somente nesta
    chamada e as credenciais são lidas do ambiente ou do ``.env``.
    """

    if fabrica_api is None:
        try:
            from siaferio import SiafeAPI
        except ImportError as erro:
            raise ErroConfiguracaoExtracao(
                "O client siaferio não está instalado neste ambiente Python."
            ) from erro
        fabrica_api = SiafeAPI

    usuario, senha = credenciais or ler_credenciais()
    with fabrica_api(usuario=usuario, senha=senha) as api:
        return consultar_dados_educacao(
            api,
            exercicio=int(exercicio),
            periodo=int(periodo),
            consulta_parte1=CONSULTA_RECEITAS,
            consulta_parte2=CONSULTA_DESPESAS,
            timeout=timeout,
            tentativas_por_consulta=tentativas_por_consulta,
            espera_inicial=espera_inicial,
        )


def persistir_dados_educacao(
    dados: Mapping[str, Any],
    exercicio: int,
    periodo: int,
    *,
    pasta_saida: str | Path = PASTA_DADOS_EXTRAIDOS,
) -> Path:
    """Publica um snapshot completo das duas consultas e retorna sua pasta.

    Cada snapshot contém JSON e CSV UTF-8 para as duas partes, além de um
    manifesto sem credenciais. Tudo é preparado em uma pasta temporária e a
    pasta final só aparece depois que todos os arquivos foram escritos com
    sucesso; assim, consumidores não encontram apenas metade da extração.
    """

    if not isinstance(dados, Mapping):
        raise TypeError("dados deve ser um mapeamento com as chaves parte1 e parte2.")
    ausentes = [chave for chave in ("parte1", "parte2") if chave not in dados]
    if ausentes:
        raise ValueError(f"Dados incompletos; chave(s) ausente(s): {', '.join(ausentes)}.")

    exercicio_numero = int(exercicio)
    periodo_numero = int(periodo)
    if periodo_numero not in range(1, 13):
        raise ValueError("periodo deve estar entre 1 e 12.")

    registros = {
        "parte1": extrair_registros(dados["parte1"]),
        "parte2": extrair_registros(dados["parte2"]),
    }
    destino_raiz = Path(pasta_saida).expanduser().resolve()
    pasta_periodo = destino_raiz / str(exercicio_numero) / f"{periodo_numero:02d}"
    pasta_periodo.mkdir(parents=True, exist_ok=True)
    instante = datetime.now(timezone.utc)
    nome_snapshot = f"extracao_{instante:%Y%m%dT%H%M%S_%fZ}_{uuid4().hex[:8]}"
    destino_final = pasta_periodo / nome_snapshot

    with tempfile.TemporaryDirectory(prefix=".extracao_", dir=pasta_periodo) as temporaria:
        pasta_temporaria = Path(temporaria)
        arquivos: dict[str, dict[str, str]] = {}
        for parte, linhas in registros.items():
            nome_json = f"{parte}.json"
            nome_csv = f"{parte}.csv"
            _gravar_json(pasta_temporaria / nome_json, linhas)
            _gravar_csv(pasta_temporaria / nome_csv, linhas)
            arquivos[parte] = {"json": nome_json, "csv": nome_csv}

        metadados = {
            "versao_formato": 1,
            "fonte": "Flexvision",
            "gerado_em_utc": instante.isoformat(),
            "exercicio": exercicio_numero,
            "periodo": periodo_numero,
            "consultas": {
                "parte1": CONSULTA_RECEITAS,
                "parte2": CONSULTA_DESPESAS,
            },
            "quantidade_registros": {
                parte: len(linhas) for parte, linhas in registros.items()
            },
            "arquivos": arquivos,
        }
        _gravar_json(pasta_temporaria / "metadados.json", metadados)

        # O destino inclui microssegundos e um sufixo aleatório, portanto não
        # substitui snapshots anteriores. A renomeação publica o conjunto.
        pasta_temporaria.replace(destino_final)

    return destino_final


def localizar_snapshot(
    exercicio: int,
    periodo: int,
    *,
    pasta_saida: str | Path = PASTA_DADOS_EXTRAIDOS,
) -> Path:
    """Retorna o snapshot completo mais recente para o ano e período."""

    exercicio_numero = int(exercicio)
    periodo_numero = int(periodo)
    if periodo_numero not in range(1, 13):
        raise ValueError("periodo deve estar entre 1 e 12.")

    pasta_periodo = (
        Path(pasta_saida).expanduser().resolve()
        / str(exercicio_numero)
        / f"{periodo_numero:02d}"
    )
    candidatos: list[tuple[datetime, str, Path]] = []
    if pasta_periodo.is_dir():
        for pasta in pasta_periodo.iterdir():
            instante = _validar_snapshot(pasta, exercicio_numero, periodo_numero)
            if instante is not None:
                candidatos.append((instante, pasta.name, pasta))

    if not candidatos:
        raise FileNotFoundError(
            f"Nenhum snapshot completo encontrado para {exercicio_numero}/{periodo_numero:02d}."
        )
    return max(candidatos)[2]


def extrair_e_persistir_dados_educacao(
    exercicio: int,
    periodo: int,
    *,
    pasta_saida: str | Path = PASTA_DADOS_EXTRAIDOS,
    timeout: int = 300,
    tentativas_por_consulta: int = 3,
    espera_inicial: float = 1.0,
    fabrica_api: Callable[..., Any] | None = None,
    credenciais: tuple[str, str] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Consulta e publica os CSVs que formam a interface obrigatória da ETL."""

    dados = extrair_dados_educacao(
        exercicio,
        periodo,
        timeout=timeout,
        tentativas_por_consulta=tentativas_por_consulta,
        espera_inicial=espera_inicial,
        fabrica_api=fabrica_api,
        credenciais=credenciais,
    )
    pasta_snapshot = persistir_dados_educacao(
        dados,
        exercicio,
        periodo,
        pasta_saida=pasta_saida,
    )
    return dados, pasta_snapshot


def _validar_snapshot(
    pasta: Path,
    exercicio: int,
    periodo: int,
) -> datetime | None:
    if not pasta.is_dir() or pasta.name.startswith("."):
        return None
    manifesto = pasta / "metadados.json"
    if not all(
        caminho.is_file()
        for caminho in (manifesto, pasta / "parte1.csv", pasta / "parte2.csv")
    ):
        return None
    try:
        metadados = json.loads(manifesto.read_text(encoding="utf-8"))
        instante = datetime.fromisoformat(metadados["gerado_em_utc"])
        arquivos = metadados["arquivos"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return None
    if (
        metadados.get("exercicio") != exercicio
        or metadados.get("periodo") != periodo
        or metadados.get("consultas")
        != {"parte1": CONSULTA_RECEITAS, "parte2": CONSULTA_DESPESAS}
        or arquivos.get("parte1", {}).get("csv") != "parte1.csv"
        or arquivos.get("parte2", {}).get("csv") != "parte2.csv"
        or instante.tzinfo is None
    ):
        return None
    return instante


def _gravar_json(caminho: Path, conteudo: Any) -> None:
    with caminho.open("x", encoding="utf-8", newline="\n") as arquivo:
        json.dump(
            conteudo,
            arquivo,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_serializar_json,
        )
        arquivo.write("\n")


def _gravar_csv(caminho: Path, registros: Sequence[Mapping[str, Any]]) -> None:
    colunas: list[str] = []
    for registro in registros:
        for coluna in registro:
            nome = str(coluna)
            if nome not in colunas:
                colunas.append(nome)

    with caminho.open("x", encoding="utf-8-sig", newline="") as arquivo:
        if not colunas:
            return
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            delimiter=";",
            lineterminator="\n",
            extrasaction="ignore",
        )
        escritor.writeheader()
        for registro in registros:
            escritor.writerow(
                {
                    coluna: _valor_csv(registro.get(coluna))
                    for coluna in colunas
                }
            )


def _valor_csv(valor: Any) -> Any:
    if valor is None:
        return ""
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, (Mapping, list, tuple)):
        return json.dumps(
            valor,
            ensure_ascii=False,
            allow_nan=False,
            default=_serializar_json,
        )
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def _serializar_json(valor: Any) -> str:
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Path):
        return str(valor)
    raise TypeError(f"Valor do tipo {type(valor).__name__} não é serializável em JSON.")


def main(argumentos: Sequence[str] | None = None) -> int:
    """Executa uma extração completa pela linha de comando."""

    parser = argparse.ArgumentParser(
        description="Extrai as consultas de educação e publica parte1.csv e parte2.csv."
    )
    parser.add_argument("exercicio", type=int, help="Exercício enviado ao Flexvision.")
    parser.add_argument(
        "periodo", type=int, choices=range(1, 13), help="Período de 1 a 12."
    )
    parser.add_argument(
        "--pasta-saida",
        type=Path,
        default=PASTA_DADOS_EXTRAIDOS,
        help="Raiz dos snapshots (padrão: dados_extraidos).",
    )
    parser.add_argument(
        "--timeout", type=int, default=300, help="Timeout de cada consulta."
    )
    opcoes = parser.parse_args(argumentos)

    _, pasta_snapshot = extrair_e_persistir_dados_educacao(
        opcoes.exercicio,
        opcoes.periodo,
        pasta_saida=opcoes.pasta_saida,
        timeout=opcoes.timeout,
    )
    print(pasta_snapshot)
    return 0


__all__ = [
    "CONSULTA_DESPESAS",
    "CONSULTA_RECEITAS",
    "ErroConfiguracaoExtracao",
    "PASTA_DADOS_EXTRAIDOS",
    "extrair_dados_educacao",
    "extrair_e_persistir_dados_educacao",
    "ler_credenciais",
    "localizar_snapshot",
    "main",
    "persistir_dados_educacao",
]


if __name__ == "__main__":
    raise SystemExit(main())
