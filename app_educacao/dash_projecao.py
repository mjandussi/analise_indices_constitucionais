"""Dashboard independente para a projeção anual da educação."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from indices_constitucionais.projecao import (
    HISTORICO_OFICIAL_INDICE,
    NOMES_MESES,
    calcular_monitor_meta,
)

from app_educacao.config import META_CONSTITUCIONAL, REAJUSTE_TOTAL_2026
from app_educacao.dados import (
    ErroDadosEducacao,
    ZERO,
    formatar_brl,
    formatar_percentual,
    processar_ultimo_snapshot,
)


def renderizar_projecao(
    parte1: dict[str, Any],
    parte2: dict[str, Any],
    exercicio: int,
    periodo: int,
) -> None:
    """Exibe um monitor indicativo, separado do cálculo oficial atual."""

    st.divider()
    with st.container(border=True):
        coluna_texto, coluna_acao = st.columns([3, 1.2], vertical_alignment="center")
        with coluna_texto:
            st.subheader("Monitor indicativo da meta anual", anchor=False)
            st.caption(
                "O acompanhamento oficial termina acima. Ative esta área para ver "
                "quanto ainda precisa ser aplicado até dezembro."
            )
        with coluna_acao:
            ativar_projecao = st.checkbox(
                "Ativar monitor anual",
                value=False,
                key="app_edu_ativar_projecao",
            )

    if not ativar_projecao:
        return

    st.header(f"Monitor da meta de Educação — {exercicio}", anchor=False)
    st.info(
        "A MDE com impostos é estimada pela média mensal liquidada. Para o "
        "FUNDEB, o monitor usa a previsão anual da Parte 1 quando disponível.",
        icon="ℹ️",
    )

    modo_base = st.radio(
        "Base constitucional anual utilizada",
        options=("Previsão anual da API", "Valor anual informado"),
        horizontal=True,
        key="app_edu_monitor_modo_base",
    )
    if modo_base == "Previsão anual da API":
        base_anual = parte1["base_prevista"]
        st.caption(
            "Base anual recomposta pela consulta 084835: "
            f"**{formatar_brl(base_anual)}**."
        )
    else:
        base_anual = Decimal(
            str(
                st.number_input(
                    "Base constitucional anual estimada",
                    min_value=0.0,
                    value=float(parte1["base_prevista"]),
                    step=1_000_000.0,
                    format="%.2f",
                    key="app_edu_monitor_base_anual",
                )
            )
        )

    metas = {
        "25,00% — mínimo constitucional": Decimal("25"),
        "25,50% — margem de segurança": Decimal("25.5"),
        "26,64% — referência histórica recente": Decimal("26.64"),
    }
    rotulo_meta = st.selectbox(
        "Meta usada no monitor",
        options=tuple(metas),
        key="app_edu_monitor_meta",
    )
    meta_percentual = metas[rotulo_meta]

    aplicar_reajuste = st.checkbox(
        "Simular reajuste sobre a MDE com impostos (exceto FUNDEB)",
        value=False,
        key="app_edu_monitor_aplicar_reajuste",
        disabled=periodo >= 12,
    )
    percentual_reajuste = ZERO
    mes_inicio_reajuste: int | None = None
    if aplicar_reajuste:
        coluna_percentual, coluna_mes = st.columns(2)
        percentual_reajuste = Decimal(
            str(
                coluna_percentual.number_input(
                    "Percentual do reajuste",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(REAJUSTE_TOTAL_2026 * Decimal("100")),
                    step=0.01,
                    format="%.2f",
                    key="app_edu_monitor_percentual_reajuste",
                    help="Percentual aplicado somente aos meses futuros alcançados.",
                )
            )
        )
        meses_futuros = tuple(range(periodo + 1, 13))
        mes_inicio_reajuste = coluna_mes.selectbox(
            "Mês de início do reajuste",
            options=meses_futuros,
            format_func=lambda mes: NOMES_MESES[mes - 1],
            key="app_edu_monitor_mes_reajuste",
        )

    try:
        monitor = calcular_monitor_meta(
            parte1,
            parte2,
            periodo,
            base_anual_estimada=base_anual,
            meta_percentual=meta_percentual,
            percentual_reajuste=percentual_reajuste,
            mes_inicio_reajuste=mes_inicio_reajuste,
        )
    except ErroDadosEducacao as erro:
        st.error(str(erro), icon="🚫")
        return

    if monitor["fundeb_estimado_por_media"]:
        st.warning(
            "A consulta da Parte 1 não trouxe o total anual previsto do FUNDEB. "
            "O monitor usou automaticamente a média mensal do FUNDEB já "
            "realizado, sem exigir valor ou percentual manual.",
            icon="⚠️",
        )

    st.caption(
        f"FUNDEB acumulado usado: **{formatar_brl(monitor['fundeb_atual'])}** "
        f"({monitor['origem_fundeb']}). Total anual projetado por "
        f"**{monitor['origem_projecao_fundeb']}**: "
        f"**{formatar_brl(monitor['fundeb_anual_projetado'])}**. Saldo previsto "
        f"até dezembro: **{formatar_brl(monitor['saldo_fundeb_ate_dezembro'])}**."
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        f"Meta monetária — {formatar_percentual(meta_percentual)}",
        formatar_brl(monitor["valor_meta"]),
        border=True,
    )
    col2.metric(
        "Aplicação projetada em dezembro",
        formatar_brl(monitor["aplicacao_projetada"]),
        border=True,
    )
    col3.metric(
        "Índice indicativo projetado",
        formatar_percentual(monitor["indice_projetado"]),
        border=True,
    )
    col4.metric(
        "Margem projetada sobre a meta",
        formatar_brl(monitor["margem_projetada"]),
        border=True,
    )

    if monitor["situacao"] == "Confortável":
        st.success(f"**Situação: confortável.** {monitor['explicacao']}", icon="✅")
    elif monitor["situacao"] == "Atenção":
        st.warning(f"**Situação: atenção.** {monitor['explicacao']}", icon="⚠️")
    else:
        st.error(f"**Situação: risco.** {monitor['explicacao']}", icon="🚨")

    st.markdown("#### Formação da estimativa para dezembro")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Componente": "MDE com impostos liquidada (exceto FUNDEB)",
                    "Cálculo": "Consulta atual",
                    "Valor": formatar_brl(monitor["mde_impostos_atual"]),
                },
                {
                    "Componente": "Transferências ao FUNDEB até o período",
                    "Cálculo": monitor["origem_fundeb"],
                    "Valor": formatar_brl(monitor["fundeb_atual"]),
                },
                {
                    "Componente": "(-) Redutores A–D já apurados",
                    "Cálculo": "Mantidos no valor atual",
                    "Valor": formatar_brl(-monitor["redutores_abcd_atual"]),
                },
                {
                    "Componente": "MDE/impostos futura (exceto FUNDEB)",
                    "Cálculo": (
                        f"{formatar_brl(monitor['media_mensal_mde'])} × "
                        f"{monitor['meses_restantes']} meses"
                    ),
                    "Valor": formatar_brl(monitor["mde_futura_estimada"]),
                },
                {
                    "Componente": "Saldo previsto de transferências ao FUNDEB",
                    "Cálculo": (
                        f"{formatar_brl(monitor['fundeb_anual_projetado'])} − "
                        f"{formatar_brl(monitor['fundeb_atual'])}"
                    ),
                    "Valor": formatar_brl(monitor["saldo_fundeb_ate_dezembro"]),
                },
                {
                    "Componente": "(+) Efeito adicional do reajuste",
                    "Cálculo": (
                        f"{formatar_brl(monitor['media_mensal_mde'])} × "
                        f"{monitor['meses_com_reajuste']} meses × "
                        f"{formatar_percentual(monitor['percentual_reajuste'])}"
                    ),
                    "Valor": formatar_brl(monitor["acrescimo_reajuste"]),
                },
                {
                    "Componente": "(=) Aplicação indicativa em dezembro",
                    "Cálculo": "Soma dos componentes projetados",
                    "Valor": formatar_brl(monitor["aplicacao_projetada"]),
                },
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    st.code(
        f"Base anual estimada = {formatar_brl(monitor['base_anual_estimada'])}\n"
        f"Meta monetária = base anual × {formatar_percentual(meta_percentual)} "
        f"= {formatar_brl(monitor['valor_meta'])}\n"
        f"Média mensal MDE/impostos = {formatar_brl(monitor['mde_impostos_atual'])} "
        f"÷ {periodo} = {formatar_brl(monitor['media_mensal_mde'])}\n"
        f"Saldo FUNDEB = previsão anual da Parte 1 − realizado = "
        f"{formatar_brl(monitor['saldo_fundeb_ate_dezembro'])}\n"
        f"Projeção sem reajuste = {formatar_brl(monitor['projecao_sem_reajuste'])}\n"
        f"Efeito adicional do reajuste = "
        f"{formatar_brl(monitor['acrescimo_reajuste'])}\n"
        f"Aplicação projetada = {formatar_brl(monitor['aplicacao_projetada'])}",
        language=None,
    )

    st.markdown("#### Referência histórica oficial")
    st.caption(
        "Valores finais publicados, usados apenas como contexto. Eles não são "
        "aplicados automaticamente na fórmula do monitor."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Ano": item["ano"],
                    "Índice oficial": formatar_percentual(item["indice"]),
                    "Margem sobre 25%": formatar_percentual(
                        item["indice"] - META_CONSTITUCIONAL
                    ),
                }
                for item in HISTORICO_OFICIAL_INDICE
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    with st.expander("Premissas e limitações", expanded=False):
        st.markdown(
            """
- A base anual padrão é a receita prevista recomposta pela consulta atual.
- A média mensal é o acumulado liquidado dividido pelo número do período consultado.
- O período deve representar a quantidade de meses efetivamente acumulada pela consulta.
- A MDE com impostos é projetada pela média mensal do próprio exercício.
- O FUNDEB realizado da Parte 1, quando disponível, é reconciliado com a Parte 2.
- O total anual do FUNDEB vem da Parte 1 quando disponível; na ausência, usa-se automaticamente a média mensal realizada.
- O reajuste nunca incide sobre o FUNDEB, independentemente da origem da projeção.
- Os redutores já apurados são mantidos constantes; novos redutores não são estimados.
- O reajuste é uma aproximação aplicada à média total da MDE; não representa cálculo de folha.
- O histórico oficial serve apenas como referência de margem.
- O monitor não consulta exercícios anteriores e não cruza dados do SIGA ou SIGRH.
"""
        )


def main() -> None:
    """Abre somente o monitor de projeção usando os CSVs já extraídos."""

    st.set_page_config(
        page_title="Projeção do Índice de Educação",
        page_icon="📈",
        layout="wide",
    )
    st.title("Projeção anual do índice de Educação")
    col_ano, col_periodo = st.columns(2)
    exercicio = int(
        col_ano.number_input("Exercício", min_value=2000, max_value=2100, value=2026)
    )
    periodo = int(
        col_periodo.selectbox("Período acumulado", options=tuple(range(1, 13)), index=3)
    )
    try:
        resultado = processar_ultimo_snapshot(exercicio, periodo)
    except (FileNotFoundError, ErroDadosEducacao) as erro:
        st.warning(
            "Extraia primeiro as consultas para este exercício/período. "
            f"Detalhe: {erro}"
        )
        return
    renderizar_projecao(
        resultado["parte1"],
        resultado["parte2"],
        exercicio,
        periodo,
    )


if __name__ == "__main__":
    main()
