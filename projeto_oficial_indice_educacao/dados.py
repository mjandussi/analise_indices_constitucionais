"""ETL dos CSVs gerados pela extração do Flexvision.

Este é o único módulo que liga os arquivos ``parte1.csv`` e ``parte2.csv``
às regras financeiras. Os dashboards recebem somente os dicionários devolvidos
por :func:`processar_csvs`.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from config import ESTAGIOS, ESTAGIOS_COMPARACAO, META_CONSTITUCIONAL
from regras.calculos import (
    calcular_parte1 as _calcular_parte1,
    calcular_parte2 as _calcular_parte2,
)
from regras.erros import ErroDadosFlexvision
from regras.normalizacao import (
    ZERO,
    formatar_brl,
    formatar_percentual,
    normalizar_texto,
    quantizar_moeda,
)


def ler_csv(caminho: str | Path) -> list[dict[str, str]]:
    """Lê o CSV da API preservando cada célula como texto."""

    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {arquivo}")

    with arquivo.open(encoding="utf-8-sig", newline="") as entrada:
        return list(csv.DictReader(entrada, delimiter=";"))


def processar_csvs(pasta_dados: str | Path) -> dict[str, Any]:
    """Calcula o índice usando exclusivamente parte1.csv e parte2.csv."""

    pasta = Path(pasta_dados).expanduser().resolve()
    parte1 = _parte1_para_dict(_calcular_parte1(ler_csv(pasta / "parte1.csv")))
    parte2 = _parte2_para_dict(_calcular_parte2(ler_csv(pasta / "parte2.csv")))
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


def _parte1_para_dict(resultado: Any) -> dict[str, Any]:
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


def _parte2_para_dict(resultado: Any) -> dict[str, Any]:
    if resultado.total_fundeb is None:
        raise ErroDadosFlexvision("O total transferido ao FUNDEB não foi calculado.")

    return {
        "linhas_brutas": [
            _linha_normalizada(indice, linha)
            for indice, linha in enumerate(resultado.linhas_normalizadas)
        ],
        "linhas_positivas": [_copiar_linha(linha) for linha in resultado.linhas_positivas],
        "total_fundeb": _copiar_linha(resultado.total_fundeb),
        "origem_total_fundeb": resultado.origem_total_fundeb,
        "valores_positivos": dict(resultado.valores_positivos),
        "redutor_a": dict(resultado.redutor_a),
        "redutor_b": dict(resultado.redutor_b),
        "redutor_c": dict(resultado.redutor_c),
        "redutor_d": dict(resultado.redutor_d),
        "outras_linhas": [_copiar_linha(linha) for linha in resultado.outras_linhas],
        "outras_deducoes": dict(resultado.outras_deducoes),
        "total_aplicado": dict(resultado.total_aplicado),
        "detalhes_a": [_copiar_recursivo(item) for item in resultado.detalhes_a],
        "detalhes_b": _copiar_recursivo(resultado.detalhes_b),
        "detalhes_c": [_copiar_recursivo(item) for item in resultado.detalhes_c],
        "detalhes_d": [_copiar_recursivo(item) for item in resultado.detalhes_d],
    }


def _copiar_linha(linha: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **{chave: valor for chave, valor in linha.items() if chave != "valores"},
        "valores": dict(linha["valores"]),
    }


def _linha_normalizada(indice: int, linha: Mapping[str, Any]) -> dict[str, Any]:
    descricao = str(linha.get("descricao", ""))
    return {
        "indice": indice,
        "descricao": descricao,
        "chave": normalizar_texto(descricao),
        "valores": {estagio: linha[estagio] for estagio in ESTAGIOS},
    }


def _copiar_recursivo(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {chave: _copiar_recursivo(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_copiar_recursivo(item) for item in valor]
    return valor


def _percentual(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    return numerador * Decimal("100") / denominador if denominador else None


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
