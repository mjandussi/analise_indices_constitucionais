"""Extrator Flexvision simples, reutilizável e sem pacotes externos.

Exemplo em Python::

    consultas = [
        {"nome": "receitas", "consulta_id": "084835", "parametros": [2026, 4]},
        {"nome": "despesas", "consulta_id": "084837", "parametros": [2026, 4]},
    ]
    arquivos_csv = extrair_consultas(consultas)

Exemplo pelo terminal::

    python extracao_flex.py -c receitas=084835 -c despesas=084837 -p 2026 4
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


URL_API = "https://siafe2-api.fazenda.rj.gov.br/siafe2-api"
TIMEOUT = 300
ARQUIVO_ENV = Path(__file__).resolve().with_name(".env")


def ler_credenciais(
    arquivo_env: str | Path = ARQUIVO_ENV,
    usuario: str | None = None,
    senha: str | None = None,
) -> tuple[str, str]:
    """Lê as credenciais informadas, do ambiente ou do arquivo .env."""

    valores: dict[str, str] = {}
    caminho = Path(arquivo_env)
    if caminho.is_file():
        for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip().strip("\"'")

    usuario = usuario or os.getenv("SIAFE_USUARIO") or valores.get("SIAFE_USUARIO")
    senha = senha or os.getenv("SIAFE_SENHA") or valores.get("SIAFE_SENHA")
    if not usuario or not senha:
        raise RuntimeError("Informe SIAFE_USUARIO e SIAFE_SENHA no arquivo .env.")
    return usuario, senha


def _requisicao_json(
    url: str,
    metodo: str = "GET",
    cabecalhos: dict[str, str] | None = None,
    corpo: dict[str, Any] | None = None,
) -> Any:
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    headers = {"Accept": "application/json", **(cabecalhos or {})}
    if corpo is not None:
        headers["Content-Type"] = "application/json"

    requisicao = Request(url, data=dados, headers=headers, method=metodo)
    with urlopen(requisicao, timeout=TIMEOUT) as resposta:
        conteudo = resposta.read()
    return json.loads(conteudo.decode("utf-8")) if conteudo else None


def autenticar(usuario: str, senha: str) -> str:
    """Autentica uma vez e devolve o cabeçalho de autorização."""

    resposta = _requisicao_json(
        f"{URL_API}/auth",
        metodo="POST",
        corpo={"usuario": usuario, "senha": senha},
    )
    token = resposta.get("token") if isinstance(resposta, dict) else None
    if not token:
        raise RuntimeError("A API não retornou o token de autenticação.")

    token = str(token).strip()
    if token.lower().startswith("bearer "):
        return token
    return f"{resposta.get('tipo') or 'Bearer'} {token}"


def consultar_flexvision(
    consulta_id: str,
    parametros: list[Any] | tuple[Any, ...] | None,
    autorizacao: str,
) -> Any:
    """Executa uma consulta Flexvision com ou sem parâmetros."""

    consulta_id = quote(str(consulta_id).strip(), safe="")
    url = f"{URL_API}/flexvision-consulta/{consulta_id}"
    if parametros:
        valores = ",".join(str(valor) for valor in parametros)
        url += "?" + urlencode({"params": valores})
    return _requisicao_json(url, cabecalhos={"Authorization": autorizacao})


def consultar_varias(
    consultas: list[dict[str, Any]],
    usuario: str | None = None,
    senha: str | None = None,
    arquivo_env: str | Path = ARQUIVO_ENV,
) -> dict[str, Any]:
    """Executa uma, duas ou mais consultas com a mesma autenticação."""

    usuario, senha = ler_credenciais(arquivo_env, usuario, senha)
    autorizacao = autenticar(usuario, senha)
    resultados: dict[str, Any] = {}

    for consulta in consultas:
        nome = str(consulta["nome"])
        resultados[nome] = consultar_flexvision(
            consulta["consulta_id"],
            consulta.get("parametros"),
            autorizacao,
        )
    return resultados


def extrair_registros(dados: Any) -> list[dict[str, Any]]:
    """Encontra as linhas do JSON que serão gravadas no CSV."""

    if dados is None:
        return []
    if isinstance(dados, dict):
        for valor in dados.values():
            if isinstance(valor, list):
                return extrair_registros(valor)
        return [{str(chave): valor for chave, valor in dados.items()}]
    if isinstance(dados, list):
        return [item if isinstance(item, dict) else {"resultado": item} for item in dados]
    return [{"resultado": dados}]


def gravar_resultados(
    resultados: dict[str, Any],
    pasta_saida: str | Path = "dados_flexvision",
) -> dict[str, Path]:
    """Grava um JSON e um CSV para cada consulta realizada."""

    pasta = Path(pasta_saida).expanduser().resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos_csv: dict[str, Path] = {}

    for nome, dados in resultados.items():
        nome_arquivo = nome.strip().replace("/", "_").replace("\\", "_")
        caminho_json = pasta / f"{nome_arquivo}.json"
        caminho_csv = pasta / f"{nome_arquivo}.csv"

        with caminho_json.open("w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)

        registros = extrair_registros(dados)
        colunas = list(dict.fromkeys(chave for linha in registros for chave in linha))
        with caminho_csv.open("w", encoding="utf-8-sig", newline="") as arquivo:
            if colunas:
                escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
                escritor.writeheader()
                for linha in registros:
                    escritor.writerow(
                        {
                            chave: json.dumps(valor, ensure_ascii=False)
                            if isinstance(valor, (dict, list))
                            else "" if valor is None else valor
                            for chave, valor in linha.items()
                        }
                    )
        arquivos_csv[nome] = caminho_csv
    return arquivos_csv


def extrair_consultas(
    consultas: list[dict[str, Any]],
    pasta_saida: str | Path = "dados_flexvision",
    usuario: str | None = None,
    senha: str | None = None,
    arquivo_env: str | Path = ARQUIVO_ENV,
) -> dict[str, Path]:
    """Executa o fluxo completo: consulta JSON e gera os CSVs."""

    resultados = consultar_varias(consultas, usuario, senha, arquivo_env)
    return gravar_resultados(resultados, pasta_saida)


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consulta o Flexvision e gera CSVs.")
    parser.add_argument(
        "-c", "--consulta", action="append", required=True, metavar="NOME=ID"
    )
    parser.add_argument("-p", "--parametros", nargs="*", default=[])
    parser.add_argument("-o", "--pasta-saida", default="dados_flexvision")
    opcoes = parser.parse_args(argumentos)

    consultas = []
    for item in opcoes.consulta:
        if "=" not in item:
            parser.error(f"Use NOME=ID em --consulta: {item}")
        nome, consulta_id = item.split("=", 1)
        consultas.append(
            {"nome": nome, "consulta_id": consulta_id, "parametros": opcoes.parametros}
        )

    for nome, caminho in extrair_consultas(consultas, opcoes.pasta_saida).items():
        print(f"{nome}: {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
