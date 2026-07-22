"""Dashboard do índice constitucional atual da Educação.

Execute com: ``streamlit run dash_indice.py``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import ESTAGIOS, META_CONSTITUCIONAL
from dados import (
    calcular_metricas,
    calcular_todos_os_indices,
    formatar_brl,
    formatar_percentual,
    processar_csvs,
)
from extracao import extrair_dados_educacao, localizar_dados_educacao


def carregar_dados(exercicio: int, periodo: int) -> dict[str, Any] | None:
    """Extrai quando solicitado; nos demais casos reutiliza o último CSV."""

    if st.button("Consultar API e gerar CSVs", type="primary"):
        try:
            with st.spinner("Consultando o Flexvision e gerando os CSVs..."):
                pasta = extrair_dados_educacao(exercicio, periodo)
        except Exception as erro:
            st.error(f"A extração falhou: {erro}")
            return None
    else:
        try:
            pasta = localizar_dados_educacao(exercicio, periodo)
        except FileNotFoundError:
            st.info("Ainda não há CSVs para este período. Use o botão acima.")
            return None

    try:
        resultado = processar_csvs(pasta)
    except Exception as erro:
        st.error(f"Não foi possível calcular os CSVs de {pasta}: {erro}")
        return None

    st.caption(f"Fonte dos cálculos: `{Path(pasta)}`")
    return resultado


def exibir_resumo(metricas: dict[str, Any]) -> None:
    """Mostra somente as quatro medidas essenciais do índice."""

    colunas = st.columns(4)
    colunas[0].metric("Índice apurado", formatar_percentual(metricas["indice_periodo"]))
    colunas[1].metric("Aplicação", formatar_brl(metricas["aplicado"]))
    colunas[2].metric("Mínimo de 25%", formatar_brl(metricas["minimo_periodo"]))
    colunas[3].metric("Saldo sobre o mínimo", formatar_brl(metricas["saldo_periodo"]))

    if metricas["atingiu_minimo"]:
        st.success("O índice apurado alcança o mínimo constitucional de 25%.")
    else:
        st.warning("O índice apurado ainda está abaixo do mínimo constitucional de 25%.")


def _criar_relogio(
    indice: Any,
    titulo: str,
    subtitulo: str,
    *,
    neutro: bool = False,
) -> go.Figure:
    """Cria um relógio com a referência fixa de 25%."""

    valor = max(0.0, float(indice))
    meta = float(META_CONSTITUCIONAL)
    limite = max(30.0, math.ceil(max(valor, meta) * 1.15 / 5) * 5)
    atingiu = indice >= META_CONSTITUCIONAL
    cor = "#15803d" if atingiu else ("#0f766e" if neutro else "#dc2626")
    cor_abaixo = "#e0f2fe" if neutro else "#fee2e2"

    figura = go.Figure(
        go.Indicator(
            mode="gauge+number" if neutro else "gauge+number+delta",
            value=valor,
            number={"suffix": "%", "valueformat": ".2f"},
            delta=None
            if neutro
            else {"reference": meta, "suffix": " p.p.", "valueformat": ".2f"},
            title={"text": f"<b>{titulo}</b><br><span>{subtitulo}</span>"},
            gauge={
                "axis": {"range": [0, limite], "ticksuffix": "%"},
                "bar": {"color": cor},
                "steps": [
                    {"range": [0, meta], "color": cor_abaixo},
                    {"range": [meta, limite], "color": "#dcfce7"},
                ],
                "threshold": {
                    "line": {"color": "#172033", "width": 4},
                    "value": meta,
                },
            },
        )
    )
    figura.update_layout(
        height=330,
        margin={"t": 60, "b": 25, "l": 30, "r": 30},
        separators=",.",
    )
    return figura


def exibir_relogios(metricas: dict[str, Any], estagio: str) -> None:
    """Compara o índice do período com o acompanhamento da previsão anual."""

    st.subheader("Índice do período e acompanhamento anual")
    st.caption(
        "O primeiro relógio usa a receita arrecadada. O segundo usa a receita "
        "anual prevista e a despesa liquidada acumulada; ele não projeta despesas futuras."
    )
    coluna_periodo, coluna_anual = st.columns(2)

    with coluna_periodo:
        if metricas["indice_periodo"] is None:
            st.info("A receita arrecadada é zero; o índice não pode ser calculado.")
        else:
            figura = _criar_relogio(
                metricas["indice_periodo"],
                "Índice do período",
                f"{ESTAGIOS[estagio]} ÷ receita arrecadada",
            )
            st.plotly_chart(figura, width="stretch", config={"displayModeBar": False})
            st.caption(
                f"Aplicação: **{formatar_brl(metricas['aplicado'])}** sobre a "
                f"receita arrecadada."
            )

    with coluna_anual:
        if metricas["indice_anual"] is None:
            st.info("A receita prevista é zero; o índice anual não pode ser calculado.")
        else:
            figura = _criar_relogio(
                metricas["indice_anual"],
                "Índice sobre a previsão anual",
                "Despesa liquidada acumulada ÷ receita prevista",
                neutro=True,
            )
            st.plotly_chart(figura, width="stretch", config={"displayModeBar": False})
            st.caption(
                f"Liquidação acumulada: **{formatar_brl(metricas['liquidado'])}**. "
                f"Execução da meta anual de 25%: "
                f"**{formatar_percentual(metricas['execucao_meta_anual'])}**."
            )


def exibir_comparacao(parte1: dict[str, Any], parte2: dict[str, Any]) -> None:
    """Compara os três estágios usados no acompanhamento."""

    linhas = calcular_todos_os_indices(parte1, parte2)
    st.subheader("Comparação por estágio")
    if any(linha["Índice (%)"] is not None for linha in linhas):
        valores = [float(linha["Índice (%)"] or 0) for linha in linhas]
        limite = max(30.0, math.ceil(max(valores + [25.0]) * 1.15 / 5) * 5)
        cores = [
            "#15803d" if linha["Atingiu 25%"] else "#dc2626" for linha in linhas
        ]
        figura = go.Figure(
            go.Bar(
                x=[linha["Estágio"] for linha in linhas],
                y=valores,
                marker_color=cores,
                text=[formatar_percentual(linha["Índice (%)"]) for linha in linhas],
                textposition="outside",
                customdata=[formatar_brl(linha["Aplicação"]) for linha in linhas],
                hovertemplate=(
                    "<b>%{x}</b><br>Índice: %{text}<br>Aplicação: %{customdata}"
                    "<extra></extra>"
                ),
            )
        )
        figura.add_hline(
            y=float(META_CONSTITUCIONAL),
            line_dash="dash",
            line_color="#172033",
            annotation_text="Mínimo de 25%",
        )
        figura.update_layout(
            height=380,
            margin={"t": 45, "b": 30, "l": 30, "r": 30},
            yaxis={"title": "Índice (%)", "range": [0, limite]},
            showlegend=False,
        )
        st.plotly_chart(figura, width="stretch", config={"displayModeBar": False})
    else:
        st.info("A receita arrecadada é zero; não há índices para comparar.")

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Estágio": linha["Estágio"],
                    "Índice": formatar_percentual(linha["Índice (%)"]),
                    "Aplicação": formatar_brl(linha["Aplicação"]),
                    "Situação": "Atingiu" if linha["Atingiu 25%"] else "Abaixo de 25%",
                }
                for linha in linhas
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def exibir_memoria(
    parte1: dict[str, Any],
    parte2: dict[str, Any],
    estagio: str,
) -> None:
    """Expõe a memória resumida para conferência do cálculo."""

    with st.expander("Memória resumida do cálculo", expanded=False):
        st.write(
            f"**Base arrecadada:** {formatar_brl(parte1['base_arrecadada'])}  "
            f"\n**25% da base:** {formatar_brl(parte1['minimo_arrecadado'])}"
        )
        itens = (
            ("Valores positivos", "valores_positivos", 1),
            ("(-) Redutor A", "redutor_a", -1),
            ("(-) Redutor B", "redutor_b", -1),
            ("(-) Redutor C", "redutor_c", -1),
            ("(-) Redutor D", "redutor_d", -1),
            ("(-) Outras deduções", "outras_deducoes", -1),
            ("(=) Total aplicado", "total_aplicado", 1),
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Componente": rotulo,
                        ESTAGIOS[estagio]: formatar_brl(
                            parte2[chave][estagio] * sinal
                        ),
                    }
                    for rotulo, chave, sinal in itens
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        if parte1["avisos"]:
            for aviso in parte1["avisos"]:
                st.warning(aviso)


def main() -> None:
    st.set_page_config(page_title="Índice de Educação", page_icon="🎓", layout="wide")
    st.title("Índice Constitucional da Educação")
    st.caption(
        "Fluxo oficial: Flexvision → JSON → CSV → regras de cálculo → dashboard. "
        "Os cálculos sempre leem os CSVs gerados pela extração."
    )

    col_ano, col_periodo, col_estagio = st.columns(3)
    exercicio = int(
        col_ano.number_input("Exercício", min_value=2020, max_value=2100, value=2026)
    )
    periodo = int(
        col_periodo.selectbox("Período", options=tuple(range(1, 13)), index=3)
    )
    estagio = col_estagio.selectbox(
        "Estágio",
        options=tuple(ESTAGIOS),
        index=tuple(ESTAGIOS).index("despesa_liquidada"),
        format_func=ESTAGIOS.get,
    )

    resultado = carregar_dados(exercicio, periodo)
    if resultado is None:
        return

    parte1, parte2 = resultado["parte1"], resultado["parte2"]
    metricas = calcular_metricas(parte1, parte2, estagio)
    exibir_resumo(metricas)
    exibir_relogios(metricas, estagio)
    exibir_comparacao(parte1, parte2)
    exibir_memoria(parte1, parte2, estagio)

    st.caption(
        f"Meta de referência: {formatar_percentual(META_CONSTITUCIONAL)}. "
        "A interpretação jurídica permanece a cargo da área responsável."
    )


if __name__ == "__main__":
    main()
