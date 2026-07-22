"""Cliente minimo para consultar o Flexvision pela API do SIAFE-Rio.

Uso:
    python flexvision_simples.py 042612 2026 7
    python flexvision_simples.py 084614
"""

import argparse
import json
import os
from urllib.parse import quote

import requests


URL_API = "https://siafe2-api.fazenda.rj.gov.br/siafe2-api"
TIMEOUT = 300


def consultar_flexvision(consulta_id, parametros=None):
    """Autentica, consulta um ID e devolve o JSON como list/dict."""
    usuario = os.getenv("SIAFE_USUARIO")
    senha = os.getenv("SIAFE_SENHA")
    if not usuario or not senha:
        raise RuntimeError(
            "Defina as variaveis de ambiente SIAFE_USUARIO e SIAFE_SENHA."
        )

    consulta_id = str(consulta_id).strip()
    if not consulta_id:
        raise ValueError("Informe o ID da consulta Flexvision.")

    with requests.Session() as sessao:
        resposta = sessao.post(
            f"{URL_API}/auth",
            json={"usuario": usuario, "senha": senha},
            timeout=TIMEOUT,
        )
        resposta.raise_for_status()

        autenticacao = resposta.json()
        token = autenticacao.get("token")
        if not token:
            raise RuntimeError("A API nao retornou o token de autenticacao.")

        tipo = autenticacao.get("tipo") or "Bearer"
        if str(token).lower().startswith("bearer "):
            sessao.headers["Authorization"] = str(token)
        else:
            sessao.headers["Authorization"] = f"{tipo} {token}"

        query = None
        if parametros:
            query = {"params": ",".join(str(valor) for valor in parametros)}

        resposta = sessao.get(
            f"{URL_API}/flexvision-consulta/{quote(consulta_id, safe='')}",
            params=query,
            timeout=TIMEOUT,
        )
        resposta.raise_for_status()
        return resposta.json() if resposta.content else None


def main():
    parser = argparse.ArgumentParser(description="Consulta o Flexvision por ID.")
    parser.add_argument("consulta_id", help="ID da consulta, incluindo zeros iniciais")
    parser.add_argument(
        "parametros",
        nargs="*",
        help="Parametros na ordem exigida pela consulta (ex.: 2026 7)",
    )
    args = parser.parse_args()

    resultado = consultar_flexvision(args.consulta_id, args.parametros)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
