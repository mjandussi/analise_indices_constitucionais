"""Dashboard separado para a projeção anual da Educação.

Execute com: ``streamlit run dash_projecao.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from config import REAJUSTE_TOTAL_2026
from dados import processar_dados_periodo
from regras.normalizacao import ZERO, formatar_brl, formatar_percentual
from regras.projecao import (
    HISTORICO_OFICIAL_INDICE,
    NOMES_MESES,
    calcular_monitor_meta,
)


def calcular_projecao_da_tela(
    parte1: dict[str, Any],
    parte2: dict[str, Any],
    periodo: int,
) -> dict[str, Any] | None:
    """Lê as três premissas editáveis e chama a regra de projeção."""

    usar_base_api = st.checkbox("Usar a base anual prevista pela API", value=True)
    if usar_base_api:
        base_anual = parte1["base_prevista"]
        st.caption(f"Base anual utilizada: {formatar_brl(base_anual)}")
    else:
        base_anual = Decimal(
            str(
                st.number_input(
                    "Base constitucional anual estimada",
                    min_value=0.01,
                    value=float(parte1["base_prevista"]),
                    step=1_000_000.0,
                    format="%.2f",
                )
            )
        )

    meta = Decimal(
        str(
            st.number_input(
                "Meta anual (%)",
                min_value=25.0,
                max_value=100.0,
                value=25.5,
                step=0.1,
                format="%.2f",
            )
        )
    )

    simular_reajuste = st.checkbox(
        "Simular reajuste na MDE futura (sem FUNDEB)",
        disabled=periodo == 12,
    )
    reajuste = ZERO
    inicio_reajuste: int | None = None
    if simular_reajuste:
        col_percentual, col_mes = st.columns(2)
        reajuste = Decimal(
            str(
                col_percentual.number_input(
                    "Reajuste (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(REAJUSTE_TOTAL_2026 * Decimal("100")),
                    step=0.01,
                    format="%.2f",
                )
            )
        )
        inicio_reajuste = col_mes.selectbox(
            "Início do reajuste",
            options=tuple(range(periodo + 1, 13)),
            format_func=lambda mes: NOMES_MESES[mes - 1],
        )

    try:
        return calcular_monitor_meta(
            parte1,
            parte2,
            periodo,
            base_anual_estimada=base_anual,
            meta_percentual=meta,
            percentual_reajuste=reajuste,
            mes_inicio_reajuste=inicio_reajuste,
        )
    except Exception as erro:
        st.error(f"Não foi possível calcular a projeção: {erro}")
        return None


def exibir_resultado(monitor: dict[str, Any]) -> None:
    """Mostra o resultado e uma memória curta da projeção."""

    colunas = st.columns(4)
    colunas[0].metric("Meta monetária", formatar_brl(monitor["valor_meta"]))
    colunas[1].metric("Aplicação projetada", formatar_brl(monitor["aplicacao_projetada"]))
    colunas[2].metric("Índice projetado", formatar_percentual(monitor["indice_projetado"]))
    colunas[3].metric("Margem projetada", formatar_brl(monitor["margem_projetada"]))

    mensagens = {
        "Confortável": st.success,
        "Atenção": st.warning,
        "Risco": st.error,
    }
    mensagens[monitor["situacao"]](
        f"Situação: {monitor['situacao']}. {monitor['explicacao']}"
    )

    st.subheader("Formação da projeção")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Componente": "Aplicação liquidada até o período",
                    "Valor": formatar_brl(monitor["liquidado_atual"]),
                },
                {
                    "Componente": "MDE/impostos estimada para os meses restantes",
                    "Valor": formatar_brl(monitor["mde_futura_estimada"]),
                },
                {
                    "Componente": "Saldo anual previsto do FUNDEB",
                    "Valor": formatar_brl(monitor["saldo_fundeb_ate_dezembro"]),
                },
                {
                    "Componente": "Efeito adicional do reajuste",
                    "Valor": formatar_brl(monitor["acrescimo_reajuste"]),
                },
                {
                    "Componente": "Aplicação projetada em dezembro",
                    "Valor": formatar_brl(monitor["aplicacao_projetada"]),
                },
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"FUNDEB projetado por: {monitor['origem_projecao_fundeb']}. "
        f"Média mensal da MDE/impostos: {formatar_brl(monitor['media_mensal_mde'])}."
    )

    with st.expander("Referência histórica", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Ano": item["ano"],
                        "Índice oficial": formatar_percentual(item["indice"]),
                    }
                    for item in HISTORICO_OFICIAL_INDICE
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def main() -> None:
    st.set_page_config(page_title="Projeção da Educação", page_icon="📈", layout="wide")
    st.title("Projeção anual do índice de Educação")
    st.caption(
        "Este painel reutiliza os CSVs já gerados por extracao.py. "
        "Ele não faz uma nova consulta à API."
    )

    col_ano, col_periodo = st.columns(2)
    exercicio = int(
        col_ano.number_input("Exercício", min_value=2020, max_value=2100, value=2026)
    )
    periodo = int(
        col_periodo.selectbox("Período acumulado", tuple(range(1, 13)), index=3)
    )

    try:
        resultado = processar_dados_periodo(exercicio, periodo)
    except Exception as erro:
        st.info(f"Gere primeiro os CSVs deste período em dash_indice.py. Detalhe: {erro}")
        return

    monitor = calcular_projecao_da_tela(
        resultado["parte1"], resultado["parte2"], periodo
    )
    if monitor is not None:
        exibir_resultado(monitor)


if __name__ == "__main__":
    main()
