"""Projeção anual da aplicação constitucional em educação.

O módulo recebe os totais já calculados das Partes 1 e 2. Ele não conhece a
origem dos dados nem a camada de apresentação: apenas projeta MDE/impostos e
FUNDEB pelo ritmo mensal observado.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_CEILING
from typing import Any

from .erros import ErroRegraNegocio
from .normalizacao import CENTAVO, ZERO, quantizar_moeda


META_CONSTITUCIONAL = Decimal("25")
TOTAL_MESES_ANO = 12
MESES_VALIDOS = range(1, TOTAL_MESES_ANO + 1)

HISTORICO_OFICIAL_INDICE = (
    {"ano": 2022, "indice": Decimal("25.70")},
    {"ano": 2023, "indice": Decimal("26.40")},
    {"ano": 2024, "indice": Decimal("26.94")},
    {"ano": 2025, "indice": Decimal("26.87")},
)

NOMES_MESES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def calcular_monitor_meta(
    parte1: Mapping[str, Any],
    parte2: Mapping[str, Any],
    periodo: int,
    *,
    base_anual_estimada: Decimal,
    meta_percentual: Decimal,
    percentual_reajuste: Decimal = ZERO,
    mes_inicio_reajuste: int | None = None,
) -> dict[str, Any]:
    """Projeta MDE/impostos e FUNDEB pelo ritmo médio mensal observado.

    ``parte1`` deve trazer ``base_arrecadada`` e pode trazer os valores
    realizado e previsto do FUNDEB. ``parte2`` deve conter os totais já
    apurados para a despesa liquidada. Todos os valores financeiros devem ser
    ``Decimal``.
    """

    if periodo not in MESES_VALIDOS:
        raise ErroRegraNegocio(f"Período inválido no monitor: {periodo}.")
    if base_anual_estimada <= ZERO:
        raise ErroRegraNegocio("A base anual estimada deve ser maior que zero.")
    if meta_percentual < META_CONSTITUCIONAL:
        raise ErroRegraNegocio("A meta gerencial não pode ser inferior a 25%.")
    if percentual_reajuste < ZERO or percentual_reajuste > Decimal("100"):
        raise ErroRegraNegocio(
            "O percentual de reajuste deve estar entre 0% e 100%."
        )
    if mes_inicio_reajuste is not None and mes_inicio_reajuste not in MESES_VALIDOS:
        raise ErroRegraNegocio(
            "O mês inicial do reajuste deve estar entre 1 e 12."
        )

    valor_meta = (
        base_anual_estimada * meta_percentual / Decimal("100")
    ).quantize(CENTAVO, rounding=ROUND_CEILING)
    liquidado_atual = parte2["total_aplicado"]["despesa_liquidada"]
    fundeb_parte2 = parte2["total_fundeb"]["valores"]["despesa_liquidada"]
    fundeb_parte1 = parte1.get("fundeb_realizado")
    fundeb_previsto = parte1.get("fundeb_previsto")
    if fundeb_parte1 is not None:
        _comparar_centavos(
            fundeb_parte1,
            fundeb_parte2,
            "FUNDEB realizado da Parte 1 versus transferido da Parte 2",
        )
        fundeb_atual = fundeb_parte1
        origem_fundeb = "Parte 1, reconciliada com a Parte 2"
    else:
        fundeb_atual = fundeb_parte2
        origem_fundeb = "Parte 2 (linha FUNDEB-FILTRO)"

    mde_impostos_atual = quantizar_moeda(
        parte2["valores_positivos"]["despesa_liquidada"]
        - fundeb_parte2
        - parte2["outras_deducoes"]["despesa_liquidada"]
    )
    if mde_impostos_atual < ZERO:
        raise ErroRegraNegocio("A MDE com recursos de impostos ficou negativa.")
    redutores_abcd_atual = quantizar_moeda(
        sum(
            (
                parte2[chave]["despesa_liquidada"]
                for chave in ("redutor_a", "redutor_b", "redutor_c", "redutor_d")
            ),
            ZERO,
        )
    )
    _comparar_centavos(
        quantizar_moeda(
            mde_impostos_atual + fundeb_atual - redutores_abcd_atual
        ),
        liquidado_atual,
        "decomposição da aplicação liquidada em MDE, FUNDEB e redutores A–D",
    )

    meses_restantes = TOTAL_MESES_ANO - periodo
    media_mensal_mde_exata = mde_impostos_atual / Decimal(periodo)
    media_mensal_mde = quantizar_moeda(media_mensal_mde_exata)
    mde_futura_estimada = quantizar_moeda(
        media_mensal_mde_exata * Decimal(meses_restantes)
    )
    if fundeb_previsto is not None:
        fundeb_anual_projetado = max(fundeb_previsto, fundeb_atual)
        origem_projecao_fundeb = "Previsão anual da Parte 1"
        fundeb_estimado_por_media = False
    else:
        fundeb_anual_projetado = quantizar_moeda(
            fundeb_atual / Decimal(periodo) * Decimal(TOTAL_MESES_ANO)
        )
        origem_projecao_fundeb = "Média mensal do FUNDEB realizado"
        fundeb_estimado_por_media = True
    saldo_fundeb_ate_dezembro = quantizar_moeda(
        fundeb_anual_projetado - fundeb_atual
    )

    primeiro_mes_futuro = periodo + 1
    inicio_efetivo_reajuste = max(
        primeiro_mes_futuro,
        mes_inicio_reajuste
        if mes_inicio_reajuste is not None
        else primeiro_mes_futuro,
    )
    meses_com_reajuste = (
        max(TOTAL_MESES_ANO + 1 - inicio_efetivo_reajuste, 0)
        if percentual_reajuste > ZERO and meses_restantes > 0
        else 0
    )
    base_automatica_reajuste = quantizar_moeda(
        media_mensal_mde_exata * Decimal(meses_com_reajuste)
    )
    acrescimo_reajuste = quantizar_moeda(
        base_automatica_reajuste * percentual_reajuste / Decimal("100")
    )

    projecao_sem_reajuste = quantizar_moeda(
        liquidado_atual + mde_futura_estimada + saldo_fundeb_ate_dezembro
    )
    aplicacao_projetada = quantizar_moeda(
        projecao_sem_reajuste + acrescimo_reajuste
    )
    valor_a_aplicar = max(quantizar_moeda(valor_meta - liquidado_atual), ZERO)
    necessidade_apos_projecao = max(
        quantizar_moeda(valor_meta - aplicacao_projetada), ZERO
    )
    margem_projetada = quantizar_moeda(aplicacao_projetada - valor_meta)
    media_mensal_necessaria = (
        (valor_a_aplicar / Decimal(meses_restantes)).quantize(
            CENTAVO, rounding=ROUND_CEILING
        )
        if meses_restantes
        else valor_a_aplicar
    )

    minimo_constitucional = quantizar_moeda(
        base_anual_estimada * META_CONSTITUCIONAL / Decimal("100")
    )
    if aplicacao_projetada >= valor_meta:
        situacao = "Confortável"
        explicacao = "O ritmo médio projetado alcança a meta escolhida."
    elif aplicacao_projetada >= minimo_constitucional:
        situacao = "Atenção"
        explicacao = "O mínimo de 25% é alcançado, mas a meta gerencial não."
    else:
        situacao = "Risco"
        explicacao = "O ritmo médio projetado não alcança o mínimo de 25%."

    return {
        "base_anual_estimada": base_anual_estimada,
        "meta_percentual": meta_percentual,
        "valor_meta": valor_meta,
        "liquidado_atual": liquidado_atual,
        "mde_impostos_atual": mde_impostos_atual,
        "redutores_abcd_atual": redutores_abcd_atual,
        "media_mensal_mde": media_mensal_mde,
        "mde_futura_estimada": mde_futura_estimada,
        "fundeb_atual": fundeb_atual,
        "fundeb_previsto_parte1": fundeb_previsto,
        "origem_fundeb": origem_fundeb,
        "origem_projecao_fundeb": origem_projecao_fundeb,
        "fundeb_estimado_por_media": fundeb_estimado_por_media,
        "fundeb_anual_projetado": fundeb_anual_projetado,
        "saldo_fundeb_ate_dezembro": saldo_fundeb_ate_dezembro,
        "percentual_reajuste": percentual_reajuste,
        "mes_inicio_reajuste": mes_inicio_reajuste,
        "meses_com_reajuste": meses_com_reajuste,
        "base_automatica_reajuste": base_automatica_reajuste,
        "acrescimo_reajuste": acrescimo_reajuste,
        "projecao_sem_reajuste": projecao_sem_reajuste,
        "aplicacao_projetada": aplicacao_projetada,
        "valor_a_aplicar": valor_a_aplicar,
        "necessidade_apos_projecao": necessidade_apos_projecao,
        "margem_projetada": margem_projetada,
        "meses_restantes": meses_restantes,
        "media_mensal_necessaria": media_mensal_necessaria,
        "indice_projetado": _percentual(
            aplicacao_projetada, base_anual_estimada
        ),
        "situacao": situacao,
        "explicacao": explicacao,
        "base_arrecadada_atual": parte1["base_arrecadada"],
    }


def _comparar_centavos(
    recebido: Decimal, calculado: Decimal, nome: str
) -> None:
    """Interrompe a projeção quando dois totais divergem mais de um centavo."""

    if abs(recebido - calculado) > CENTAVO:
        raise ErroRegraNegocio(
            f"Divergência em {nome}: recebido={recebido}, calculado={calculado}."
        )


def _percentual(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    """Calcula um percentual na escala 0–100."""

    return numerador * Decimal("100") / denominador if denominador else None


__all__ = [
    "HISTORICO_OFICIAL_INDICE",
    "META_CONSTITUCIONAL",
    "MESES_VALIDOS",
    "NOMES_MESES",
    "TOTAL_MESES_ANO",
    "calcular_monitor_meta",
]
