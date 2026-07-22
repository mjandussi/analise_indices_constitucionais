"""Pequenos adaptadores de apresentação, sem dependência do Streamlit."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from indices_constitucionais.erros import ErroConsultaFlexvision, ErroDadosFlexvision

from app_educacao.config import ESTAGIOS
from app_educacao.dados import CENTAVO, formatar_brl, moeda


def formatar_brl_compacto(valor: Decimal | None) -> str:
    """Abrevia milhões e bilhões somente para os cards da interface."""

    if valor is None:
        return "—"
    absoluto = abs(valor)
    if absoluto >= Decimal("1000000000"):
        divisor, sufixo = Decimal("1000000000"), "bi"
    elif absoluto >= Decimal("1000000"):
        divisor, sufixo = Decimal("1000000"), "mi"
    else:
        return formatar_brl(valor)
    reduzido = (valor / divisor).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    numero = (
        f"{reduzido:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    )
    return f"R$ {numero} {sufixo}"


def linha_financeira(
    rotulo: str, valores: Mapping[str, Decimal]
) -> dict[str, str]:
    """Converte uma série ``Decimal`` em uma linha pronta para tabela."""

    return {
        "Componente": rotulo,
        **{
            ESTAGIOS[estagio]: formatar_brl(valores[estagio])
            for estagio in ESTAGIOS
        },
    }


def quadro_formacao_aplicacao(parte2: Mapping[str, Any]) -> list[dict[str, str]]:
    """Memória da fórmula positivos - A - B - C - D - outras deduções."""

    return [
        linha_financeira("(+) Valores positivos", parte2["valores_positivos"]),
        linha_financeira("(-) A — superávit anterior", parte2["redutor_a"]),
        linha_financeira(
            "(-) B — FUNDEB não aplicado acima de 10%", parte2["redutor_b"]
        ),
        linha_financeira("(-) C — RP cancelados MDE", parte2["redutor_c"]),
        linha_financeira("(-) D — RP cancelados TAC", parte2["redutor_d"]),
        linha_financeira("(-) Outras deduções", parte2["outras_deducoes"]),
        linha_financeira(
            "(=) Total aplicado em educação", parte2["total_aplicado"]
        ),
    ]


def relatorio_calculado(parte2: Mapping[str, Any]) -> list[dict[str, str]]:
    """Recria o desenho lógico do relatório após calcular A–D em Python."""

    linhas = [
        linha_financeira(linha["descricao"], linha["valores"])
        for linha in parte2["linhas_positivas"]
    ]
    linhas.extend(
        [
            linha_financeira(
                "(-) A — superávit permitido anterior não aplicado",
                parte2["redutor_a"],
            ),
            linha_financeira(
                "(-) B — receitas do FUNDEB não utilizadas acima de 10%",
                parte2["redutor_b"],
            ),
        ]
    )
    linhas.extend(
        linha_financeira(linha["descricao"], linha["valores"])
        for linha in parte2["outras_linhas"]
    )
    redutor_c_d = {
        estagio: moeda(
            parte2["redutor_c"][estagio] + parte2["redutor_d"][estagio]
        )
        for estagio in ESTAGIOS
    }
    linhas.extend(
        [
            linha_financeira(
                "(-) Restos a Pagar Cancelados (C + D)", redutor_c_d
            ),
            linha_financeira(
                "(I) Total dos Restos a Pagar Cancelados — MDE",
                parte2["redutor_c"],
            ),
            linha_financeira(
                "(II) Restos a Pagar Cancelados — TAC", parte2["redutor_d"]
            ),
            linha_financeira(
                "VALOR TOTAL DESTINADO À EDUCAÇÃO", parte2["total_aplicado"]
            ),
        ]
    )
    return linhas


def formula_monetaria(parte2: Mapping[str, Any], estagio: str) -> str:
    """Fórmula da aplicação preenchida com valores do estágio selecionado."""

    return (
        f"{formatar_brl(parte2['valores_positivos'][estagio])}"
        f" - {formatar_brl(parte2['redutor_a'][estagio])}"
        f" - {formatar_brl(parte2['redutor_b'][estagio])}"
        f" - {formatar_brl(parte2['redutor_c'][estagio])}"
        f" - {formatar_brl(parte2['redutor_d'][estagio])}"
        f" - {formatar_brl(parte2['outras_deducoes'][estagio])}"
        f" = {formatar_brl(parte2['total_aplicado'][estagio])}"
    )


def diagnostico_seguro(erro: Exception) -> str:
    """Produz uma mensagem útil sem exibir senha, token ou payload integral."""

    if isinstance(erro, (ErroConsultaFlexvision, ErroDadosFlexvision)):
        return str(erro)
    if erro.__class__.__name__ == "SiafeAuthenticationError":
        return "O SIAFE-Rio recusou a autenticação. Confira as credenciais do .env."
    return (
        "Ocorreu uma falha inesperada durante a consulta ou o cálculo. "
        "Consulte o terminal do servidor sem compartilhar credenciais."
    )
