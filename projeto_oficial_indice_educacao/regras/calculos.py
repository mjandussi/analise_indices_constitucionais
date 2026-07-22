"""Cálculo do índice de Educação com a mesma lógica de uma planilha.

O fluxo é propositalmente direto:

1. a Parte 1 já chega pronta e fornece a base e o mínimo de 25%;
2. a Parte 2 adaptada fornece os dados brutos de A, B, C, D e FUNDEB;
3. o pandas monta uma tabela equivalente à Parte 2 original;
4. somam-se as linhas ``(+)`` e subtraem-se as linhas ``(-)``.

Os DataFrames organizam as linhas. Os valores monetários continuam como
``Decimal`` para não perder centavos.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pandas as pd

from config import ESTAGIOS
from .erros import ErroRegraNegocio, ErroSchemaFlexvision
from .normalizacao import ZERO, normalizar_texto, quantizar_moeda


COLUNAS_VALORES = tuple(ESTAGIOS)

TITULO_A = (
    "(-) SUPERÁVIT PERMITIDO NO EXERCÍCIO IMEDIATAMENTE ANTERIOR "
    "NÃO APLICADO ATÉ O PRIMEIRO QUADRIMESTRE DO EXERCÍCIO ATUAL"
)
TITULO_B = (
    "(-) RECEITAS DO FUNDEB NÃO UTILIZADAS NO EXERCÍCIO, "
    "EM VALOR SUPERIOR A 10%"
)
TITULO_C_D = "(-) Restos a Pagar Cancelados (I) - (II)"
TITULO_C = "(I) Total dos Restos a Pagar Cancelados - MDE"
TITULO_D = (
    "(II) Restos a Pagar Cancelados - item 5.3.1 do TAC - "
    "(Ação Civil Pública 0054872- 30.2018.8.19.0001)"
)
TITULO_TOTAL = "VALOR TOTAL DESTINADO A APLICAÇÃO EM EDUCAÇÃO (II)"


def calcular_parte1(tabela: pd.DataFrame) -> dict[str, Any]:
    """Lê os totais da Parte 1, que já chegam calculados pelo Flexvision."""

    total = _uma_linha(
        tabela,
        tabela["chave"].str.startswith("TOTAL - BASE DE CALCULO"),
        "TOTAL - BASE DE CÁLCULO",
    )
    minimo = _uma_linha(
        tabela,
        tabela["chave"].str.contains("VALOR A SER APLICADO EM EDUCACAO", regex=False),
        "VALOR A SER APLICADO EM EDUCAÇÃO",
    )

    fundeb = tabela[
        tabela["chave"].str.contains("TOTAL DESTINADO AO FUNDEB", regex=False)
    ]
    fundeb_previsto = None
    fundeb_realizado = None
    if len(fundeb) > 1:
        raise ErroSchemaFlexvision("Há mais de uma linha TOTAL DESTINADO AO FUNDEB.")
    if len(fundeb) == 1:
        fundeb_previsto = quantizar_moeda(fundeb.iloc[0]["prevista"])
        fundeb_realizado = quantizar_moeda(fundeb.iloc[0]["arrecadada"])

    return {
        "base_prevista": quantizar_moeda(total["prevista"]),
        "base_arrecadada": quantizar_moeda(total["arrecadada"]),
        "diferenca": quantizar_moeda(total["diferenca"]),
        "realizacao_percentual": total["percentual"],
        "minimo_previsto": quantizar_moeda(minimo["prevista"]),
        "minimo_arrecadado": quantizar_moeda(minimo["arrecadada"]),
        "fundeb_previsto": fundeb_previsto,
        "fundeb_realizado": fundeb_realizado,
        "avisos": [],
    }


def calcular_parte2(adaptada: pd.DataFrame) -> dict[str, Any]:
    """Transforma a Parte 2 adaptada em uma tabela equivalente à original."""

    # 1) Calcula as linhas que existiam consolidadas na consulta original.
    fundeb, origem_fundeb = _calcular_fundeb(adaptada)
    redutor_a = _calcular_redutor_a(adaptada)
    redutor_b = _calcular_redutor_b(adaptada)
    redutor_c = _calcular_redutor_c(adaptada)
    redutor_d = _calcular_redutor_d(adaptada)
    redutor_c_d = _somar_valores(redutor_c, redutor_d)

    # 2) Mantém as fontes positivas e as deduções comuns da consulta.
    eh_fundeb = adaptada["chave"].str.contains(
        "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB", regex=False
    )
    positivas = adaptada[
        adaptada["chave"].str.startswith("(+)") & ~eh_fundeb
    ].copy()
    # Se uma exportação híbrida também trouxer as antigas linhas consolidadas,
    # elas são ignoradas aqui para A, B e C+D não entrarem duas vezes.
    chave = adaptada["chave"]
    eh_consolidada_antiga = (
        chave.str.contains("SUPERAVIT PERMITIDO NO EXERCICIO", regex=False)
        | chave.str.contains(
            "RECEITAS DO FUNDEB NAO UTILIZADAS NO EXERCICIO", regex=False
        )
        | chave.str.contains("RESTOS A PAGAR CANCELADOS (I) - (II)", regex=False)
    )
    outras = adaptada[
        chave.str.startswith("(-)") & ~eh_consolidada_antiga
    ].copy()
    _exigir_nao_negativos(positivas, "fontes positivas")
    _exigir_nao_negativos(outras, "demais deduções")

    # 3) Monta a Parte 2 calculada na mesma ordem visual da consulta original.
    tabela_calculada = pd.concat(
        [
            positivas,
            _linha_calculada(
                "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB", fundeb
            ),
            _linha_calculada(TITULO_A, redutor_a),
            _linha_calculada(TITULO_B, redutor_b),
            outras,
            _linha_calculada(TITULO_C_D, redutor_c_d),
            _linha_calculada(TITULO_C, redutor_c),
            _linha_calculada(TITULO_D, redutor_d),
        ],
        ignore_index=True,
    )

    # 4) Faz exatamente a conta que seria feita no Excel.
    linhas_positivas = tabela_calculada[
        tabela_calculada["chave"].str.startswith("(+)")
    ]
    linhas_negativas = tabela_calculada[
        tabela_calculada["chave"].str.startswith("(-)")
    ]
    valores_positivos = _somar_linhas(linhas_positivas)
    valores_negativos = _somar_linhas(linhas_negativas)
    total_aplicado = {
        coluna: quantizar_moeda(
            valores_positivos[coluna] - valores_negativos[coluna]
        )
        for coluna in COLUNAS_VALORES
    }
    if any(valor < ZERO for valor in total_aplicado.values()):
        raise ErroRegraNegocio(
            "O total aplicado ficou negativo; confira os sinais da Parte 2."
        )

    tabela_calculada = pd.concat(
        [tabela_calculada, _linha_calculada(TITULO_TOTAL, total_aplicado)],
        ignore_index=True,
    )

    outras_deducoes = _somar_linhas(outras)
    return {
        "tabela_calculada": _registros_simples(tabela_calculada),
        "total_fundeb": {
            "descricao": "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
            "valores": fundeb,
        },
        "origem_total_fundeb": origem_fundeb,
        "valores_positivos": valores_positivos,
        "redutor_a": redutor_a,
        "redutor_b": redutor_b,
        "redutor_c": redutor_c,
        "redutor_d": redutor_d,
        "outras_deducoes": outras_deducoes,
        "total_aplicado": total_aplicado,
    }


def _calcular_fundeb(tabela: pd.DataFrame) -> tuple[dict[str, Decimal], str]:
    """Obtém o FUNDEB positivo, pronto ou por ``0 - FUNDEB-FILTRO``."""

    eh_total = tabela["chave"].str.contains(
        "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB", regex=False
    )
    direta = tabela[eh_total & ~tabela["chave"].str.contains("FILTRO", regex=False)]
    filtro = tabela[
        tabela["chave"].str.contains("FUNDEB", regex=False)
        & tabela["chave"].str.contains("FILTRO", regex=False)
    ]

    if len(direta) > 1 or len(filtro) > 1:
        raise ErroSchemaFlexvision("Há mais de uma linha de total do FUNDEB.")
    if direta.empty and filtro.empty:
        raise ErroSchemaFlexvision(
            "A Parte 2 precisa do total positivo do FUNDEB ou do FUNDEB-FILTRO."
        )

    valor_direto = None
    valor_filtro = None
    if not direta.empty:
        _exigir_nao_negativos(direta, "total positivo do FUNDEB")
        valor_direto = _valores_da_linha(direta.iloc[0])
    if not filtro.empty:
        valores = _valores_da_linha(filtro.iloc[0])
        if any(valor > ZERO for valor in valores.values()):
            raise ErroRegraNegocio("O FUNDEB-FILTRO deve chegar negativo ou zerado.")
        valor_filtro = {
            coluna: quantizar_moeda(ZERO - valor) for coluna, valor in valores.items()
        }

    if valor_direto is not None and valor_filtro is not None:
        if valor_direto != valor_filtro:
            raise ErroRegraNegocio(
                "O total direto do FUNDEB diverge do cálculo 0 - FUNDEB-FILTRO."
            )
        return valor_direto, "linha direta conferida com FUNDEB-FILTRO"
    if valor_direto is not None:
        return valor_direto, "linha direta TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
    return valor_filtro or _serie_zero(), "0 - linha FUNDEB-FILTRO"


def _calcular_redutor_a(tabela: pd.DataFrame) -> dict[str, Decimal]:
    """A = soma de ``máximo(superávit - aplicação, zero)``."""

    total = _serie_zero()
    grupos = {
        "impostos": "IMPOSTOS",
        "complementacao_uniao": "COMPLEMENTACAO DA UNIAO",
    }
    for grupo, texto_grupo in grupos.items():
        pertence = tabela["chave"].str.contains(texto_grupo, regex=False)
        superavit = _uma_linha(
            tabela,
            pertence
            & tabela["chave"].str.contains("SUPERAVIT FINANCEIRO", regex=False),
            f"superávit do grupo {grupo}",
        )
        aplicacao = _uma_linha(
            tabela,
            pertence
            & tabela["chave"].str.contains("APLICACAO DO SUPERAVIT", regex=False),
            f"aplicação do superávit do grupo {grupo}",
        )
        _exigir_nao_negativos(
            pd.DataFrame([superavit, aplicacao]), f"insumos do redutor A ({grupo})"
        )
        calculado = {
            coluna: quantizar_moeda(max(superavit[coluna] - aplicacao[coluna], ZERO))
            for coluna in COLUNAS_VALORES
        }
        total = _somar_valores(total, calculado)
    return total


def _calcular_redutor_b(tabela: pd.DataFrame) -> dict[str, Decimal]:
    """B = máximo(receita - despesa - 10% da receita, zero)."""

    receita = _uma_linha(
        tabela,
        tabela["chave"].str.contains("RECEITAS RECEBIDAS DO FUNDEB", regex=False)
        & ~tabela["chave"].str.contains("NAO UTILIZADAS", regex=False),
        "receitas recebidas do FUNDEB",
    )
    despesa = _uma_linha(
        tabela,
        tabela["chave"].str.contains(
            "TOTAL DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB", regex=False
        ),
        "despesas custeadas com FUNDEB",
    )
    _exigir_nao_negativos(pd.DataFrame([receita, despesa]), "insumos do redutor B")

    receita_valores = _valores_da_linha(receita)
    despesa_valores = _valores_da_linha(despesa)
    redutor = {
        coluna: quantizar_moeda(
            max(
                receita_valores[coluna]
                - despesa_valores[coluna]
                - receita_valores[coluna] * Decimal("0.10"),
                ZERO,
            )
        )
        for coluna in COLUNAS_VALORES
    }
    return redutor


def _calcular_redutor_c(tabela: pd.DataFrame) -> dict[str, Decimal]:
    """C = soma anual de ``máximo(RP cancelado - excesso, zero)``."""

    rp = tabela[
        tabela["chave"].str.contains("RESTOS A PAGAR CANCELADOS", regex=False)
        & (
            tabela["chave"].str.contains("RPP", regex=False)
            | tabela["chave"].str.contains("RPNP", regex=False)
        )
        & ~tabela["chave"].str.contains("TAC", regex=False)
    ]
    excesso = tabela[
        tabela["chave"].str.contains("EXCESSO APLICADO EM EDUCACAO", regex=False)
    ]
    if rp.empty and excesso.empty:
        raise ErroSchemaFlexvision("Não foram encontrados os dados anuais do redutor C.")

    restos_por_ano = _linhas_por_ano(rp, "RP cancelado")
    excessos_por_ano = _linhas_por_ano(excesso, "excesso aplicado")
    total = _serie_zero()
    for ano in sorted(set(restos_por_ano) | set(excessos_por_ano)):
        restos = restos_por_ano.get(ano, _serie_zero())
        excessos = excessos_por_ano.get(ano, _serie_zero())
        calculado = {
            coluna: quantizar_moeda(max(restos[coluna] - excessos[coluna], ZERO))
            for coluna in COLUNAS_VALORES
        }
        total = _somar_valores(total, calculado)
    return total


def _calcular_redutor_d(tabela: pd.DataFrame) -> dict[str, Decimal]:
    """D = soma dos RPs cancelados vinculados ao TAC."""

    tac = tabela[
        tabela["chave"].str.contains("RP CANCELADO TAC", regex=False)
    ]
    if tac.empty:
        raise ErroSchemaFlexvision("Não foram encontrados os dados do redutor D (TAC).")
    _exigir_nao_negativos(tac, "insumos do redutor D")
    return _somar_linhas(tac)


def _uma_linha(
    tabela: pd.DataFrame, filtro: pd.Series, nome: str
) -> pd.Series:
    linhas = tabela[filtro]
    if len(linhas) != 1:
        raise ErroSchemaFlexvision(
            f"Era esperada uma linha para {nome}; foram encontradas {len(linhas)}."
        )
    return linhas.iloc[0]


def _exigir_nao_negativos(tabela: pd.DataFrame, nome: str) -> None:
    for coluna in COLUNAS_VALORES:
        if any(valor < ZERO for valor in tabela[coluna]):
            raise ErroRegraNegocio(f"Há valor negativo em {nome}, coluna {ESTAGIOS[coluna]}.")


def _linha_calculada(
    descricao: str, valores: dict[str, Decimal]
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "indice": None,
                "descricao": descricao,
                "chave": normalizar_texto(descricao),
                **valores,
            }
        ]
    )


def _somar_linhas(tabela: pd.DataFrame) -> dict[str, Decimal]:
    return {
        coluna: quantizar_moeda(sum(tabela[coluna].tolist(), ZERO))
        for coluna in COLUNAS_VALORES
    }


def _somar_valores(
    primeiro: dict[str, Decimal], segundo: dict[str, Decimal]
) -> dict[str, Decimal]:
    return {
        coluna: quantizar_moeda(primeiro[coluna] + segundo[coluna])
        for coluna in COLUNAS_VALORES
    }


def _serie_zero() -> dict[str, Decimal]:
    return {coluna: ZERO for coluna in COLUNAS_VALORES}


def _valores_da_linha(linha: pd.Series) -> dict[str, Decimal]:
    return {coluna: quantizar_moeda(linha[coluna]) for coluna in COLUNAS_VALORES}


def _linhas_por_ano(
    tabela: pd.DataFrame, nome: str
) -> dict[int, dict[str, Decimal]]:
    resultado: dict[int, dict[str, Decimal]] = {}
    _exigir_nao_negativos(tabela, nome)
    for _, linha in tabela.iterrows():
        ano = _extrair_ano(linha["chave"])
        if ano is None:
            raise ErroSchemaFlexvision(
                f"Não foi encontrado o ano na linha {linha['descricao']!r}."
            )
        if ano in resultado:
            raise ErroSchemaFlexvision(f"Há mais de uma linha de {nome} para {ano}.")
        resultado[ano] = _valores_da_linha(linha)
    return resultado


def _extrair_ano(texto: str) -> int | None:
    anos = re.findall(r"\b(?:19|20)\d{2}\b", texto)
    return int(anos[-1]) if anos else None


def _registros_simples(tabela: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "descricao": linha["descricao"],
            **{coluna: linha[coluna] for coluna in COLUNAS_VALORES},
        }
        for _, linha in tabela.iterrows()
    ]


__all__ = ["calcular_parte1", "calcular_parte2"]
