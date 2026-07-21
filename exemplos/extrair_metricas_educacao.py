"""Exemplo de extração das consultas e cálculo das métricas de educação."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from siaferio import SiafeAPI

from indices_constitucionais import (
    consultar_e_calcular_educacao,
    formatar_brl,
    formatar_percentual,
)


def main() -> None:
    load_dotenv()
    usuario = os.getenv("SIAFE_USUARIO")
    senha = os.getenv("SIAFE_SENHA")
    if not usuario or not senha:
        raise RuntimeError("Defina SIAFE_USUARIO e SIAFE_SENHA no arquivo .env.")

    with SiafeAPI(usuario=usuario, senha=senha) as api:
        resultado = consultar_e_calcular_educacao(
            api,
            exercicio=2026,
            periodo=4,
            estagio_indice="despesa_liquidada",
        )

    metricas = resultado.metricas_dashboard()
    print(f"Base arrecadada: {formatar_brl(metricas['receita_arrecadada'])}")
    print(f"Mínimo constitucional: {formatar_brl(metricas['minimo_constitucional'])}")
    print(f"Aplicação líquida: {formatar_brl(metricas['aplicacao_educacao'])}")
    print(f"Índice: {formatar_percentual(metricas['indice_aplicacao_percentual'])}")
    print(f"Atingiu 25%: {'sim' if metricas['atingiu_minimo'] else 'não'}")


if __name__ == "__main__":
    main()
