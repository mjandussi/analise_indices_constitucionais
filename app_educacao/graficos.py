"""Cards e gráficos do dashboard do índice de educação."""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import altair as alt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_educacao.config import ESTAGIOS, ESTAGIOS_COMPARACAO, META_CONSTITUCIONAL
from app_educacao.apresentacao import formatar_brl_compacto
from app_educacao.dados import (
    CENTAVO,
    ZERO,
    calcular_todos_os_indices,
    formatar_brl,
    formatar_percentual,
)


def criar_relogio(
    valor: Decimal,
    *,
    titulo: str,
    subtitulo: str,
    neutro: bool,
) -> go.Figure:
    """Relógio com uma marca fixa em 25%.

    No relógio do período, vermelho/verde comunica a relação com o limite. Na
    visão anual intermediária, ``neutro=True`` usa azul abaixo de 25% para não
    sugerir uma conclusão jurídica antecipada sobre o encerramento do exercício.
    """

    # Apresentação: Plotly exige float. Esta cópia é usada só para desenhar; a
    # decisão de atingimento abaixo continua sendo feita com o Decimal original.
    valor_float = max(0.0, float(valor))
    meta = float(META_CONSTITUCIONAL)
    eixo_maximo = max(30.0, math.ceil(max(valor_float, meta) * 1.15 / 5.0) * 5.0)
    atingiu = valor >= META_CONSTITUCIONAL
    cor = "#15803d" if atingiu else ("#0f766e" if neutro else "#dc2626")
    passos = (
        [
            {"range": [0, meta], "color": "#e0f2fe"},
            {"range": [meta, eixo_maximo], "color": "#dcfce7"},
        ]
        if neutro
        else [
            {"range": [0, meta], "color": "#fee2e2"},
            {"range": [meta, eixo_maximo], "color": "#dcfce7"},
        ]
    )
    indicador: dict[str, Any] = {
        "mode": "gauge+number" if neutro else "gauge+number+delta",
        "value": valor_float,
        "number": {"suffix": "%", "valueformat": ".2f", "font": {"size": 45, "color": cor}},
        "title": {
            "text": f"<b>{titulo}</b><br><span style='font-size:13px'>{subtitulo}</span>",
            "font": {"size": 17},
        },
        "gauge": {
            "axis": {
                "range": [0, eixo_maximo],
                "ticksuffix": "%",
                "tickformat": ".0f",
                "tickfont": {"size": 11},
            },
            "bar": {"color": cor, "thickness": 0.38},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 1,
            "bordercolor": "#cbd5e1",
            "steps": passos,
            "threshold": {
                "line": {"color": "#0f172a", "width": 4},
                "thickness": 0.85,
                "value": meta,
            },
        },
    }
    if not neutro:
        indicador["delta"] = {
            "reference": meta,
            "relative": False,
            "valueformat": ".2f",
            "suffix": " p.p. ante 25%",
            "increasing": {"color": "#15803d"},
            "decreasing": {"color": "#dc2626"},
        }
    figura = go.Figure(go.Indicator(**indicador))
    figura.update_layout(
        height=340,
        margin=dict(t=75, b=35, l=25, r=25),
        paper_bgcolor="rgba(0,0,0,0)",
        separators=",.",
        font=dict(color="#172033"),
    )
    return figura


def formatar_margem(valor: Decimal | None) -> str | None:
    """Formata a distância para 25 em pontos percentuais (p.p.)."""

    if valor is None:
        return None
    numero = valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    sinal = "+" if numero > ZERO else ""
    return f"{sinal}{str(numero).replace('.', ',')} p.p. ante 25%"


def renderizar_cards(metricas: dict[str, Any], estagio: str) -> None:
    """Resume índice, aplicação, mínimo e diferença monetária do período.

    Todos os cards desta faixa usam o estágio selecionado. A margem é a
    diferença percentual para 25%; falta/excedente é a diferença em reais.
    """

    saldo = metricas["saldo_periodo"]
    if saldo < ZERO:
        saldo_rotulo = "Falta para o mínimo do período"
        saldo_valor = metricas["deficit_periodo"]
    elif saldo > ZERO:
        saldo_rotulo = "Excedente sobre o mínimo do período"
        saldo_valor = metricas["excedente_periodo"]
    else:
        saldo_rotulo = "Saldo do mínimo do período"
        saldo_valor = ZERO

    cards = (
        (
            "Índice do período — base arrecadada",
            formatar_percentual(metricas["indice_periodo"]),
            formatar_margem(metricas["margem_pp"]),
            "Aplicação do estágio dividida pela receita arrecadada.",
        ),
        (
            f"Aplicação — {ESTAGIOS[estagio]}",
            formatar_brl_compacto(metricas["aplicado"]),
            None,
            f"Valor após todos os redutores: {formatar_brl(metricas['aplicado'])}.",
        ),
        (
            "Mínimo do período — 25% da arrecadada",
            formatar_brl_compacto(metricas["minimo_periodo"]),
            None,
            f"Valor exato: {formatar_brl(metricas['minimo_periodo'])}.",
        ),
        (
            saldo_rotulo,
            formatar_brl_compacto(saldo_valor),
            None,
            f"Diferença exata: {formatar_brl(saldo_valor)}.",
        ),
    )
    for coluna, (rotulo, valor, delta, ajuda) in zip(st.columns(4), cards):
        with coluna:
            st.metric(
                rotulo,
                valor,
                delta=delta,
                help=ajuda,
                border=True,
                width="stretch",
            )

    if metricas["indice_periodo"] is None:
        st.warning("A receita arrecadada é zero; o índice não pode ser calculado.", icon="⚠️")
    elif metricas["atingiu_minimo"]:
        st.success(
            f"**Percentual do estágio ≥ 25%** — {ESTAGIOS[estagio]} atingiu o mínimo.",
            icon="✅",
        )
    else:
        st.error(
            f"**Percentual do estágio < 25%** — {ESTAGIOS[estagio]} ainda está abaixo do mínimo.",
            icon="📉",
        )


def renderizar_relogios(metricas: dict[str, Any], estagio: str) -> None:
    """Coloca lado a lado a apuração do período e o acompanhamento anual."""

    st.subheader("Visão do período e da meta anual prevista", anchor=False)
    st.caption(
        "À esquerda, a base é a receita já arrecadada. À direita, a base é toda a "
        "receita prevista para o exercício e o numerador é sempre a despesa liquidada."
    )
    coluna_periodo, coluna_anual = st.columns(2)

    with coluna_periodo:
        if metricas["indice_periodo"] is None:
            st.info("A receita arrecadada é zero; o relógio do período está indisponível.")
        else:
            st.plotly_chart(
                criar_relogio(
                    metricas["indice_periodo"],
                    titulo="Índice do período",
                    subtitulo=f"{ESTAGIOS[estagio]} ÷ receita arrecadada",
                    neutro=False,
                ),
                width="stretch",
                key="app_edu_relogio_periodo",
                config={"displayModeBar": False},
            )
            st.caption(
                f"Cobertura do mínimo do período: "
                f"**{formatar_percentual(metricas['cobertura_minimo'])}** — "
                f"{formatar_brl(metricas['aplicado'])} de "
                f"{formatar_brl(metricas['minimo_periodo'])}."
            )

    with coluna_anual:
        if metricas["indice_anual"] is None:
            st.info("A receita prevista é zero; o relógio anual está indisponível.")
        else:
            st.plotly_chart(
                criar_relogio(
                    metricas["indice_anual"],
                    titulo="Índice sobre a previsão anual",
                    subtitulo="Despesa liquidada ÷ receita prevista",
                    neutro=True,
                ),
                width="stretch",
                key="app_edu_relogio_anual",
                config={"displayModeBar": False},
            )
            st.caption(
                f"Índice sobre a receita prevista: **{formatar_percentual(metricas['indice_anual'])}**. "
                f"Execução da meta anual de 25%: "
                f"**{formatar_percentual(metricas['execucao_meta_anual'])}** — "
                f"{formatar_brl(metricas['liquidado'])} de "
                f"{formatar_brl(metricas['minimo_anual'])}."
            )

    saldo_anual = metricas["saldo_anual"]
    if saldo_anual < ZERO:
        saldo_rotulo = "Falta para a meta anual prevista"
        saldo_valor = metricas["deficit_anual"]
    else:
        saldo_rotulo = "Excedente sobre a meta anual prevista"
        saldo_valor = metricas["excedente_anual"]

    st.markdown("#### Valores da previsão anual")
    cards_anuais = (
        ("Receita prevista", metricas["base_prevista"]),
        ("Meta anual prevista — 25%", metricas["minimo_anual"]),
        ("Despesa liquidada acumulada", metricas["liquidado"]),
        ("Execução da meta anual", metricas["execucao_meta_anual"]),
        (saldo_rotulo, saldo_valor),
    )
    for coluna, (rotulo, valor) in zip(st.columns(5), cards_anuais):
        with coluna:
            if isinstance(valor, Decimal) and "Execução" in rotulo:
                exibido = formatar_percentual(valor)
            else:
                exibido = formatar_brl_compacto(valor)
            st.metric(rotulo, exibido, border=True, width="stretch")
    st.caption(
        "A visão anual é gerencial. Ela compara a liquidação acumulada com 25% da "
        "receita prevista e não substitui a apuração pela receita arrecadada."
    )


def renderizar_comparacao(parte1: dict[str, Any], parte2: dict[str, Any]) -> None:
    """Compara empenhada, liquidada e paga sobre a mesma receita arrecadada."""

    st.subheader("Comparação entre estágios", anchor=False)
    st.caption(
        "A linha tracejada é o mínimo de 25%. O gráfico mostra somente despesa "
        "empenhada (obrigação assumida), liquidada (entrega reconhecida) e paga "
        "(saída financeira). Todas usam a mesma receita arrecadada como base."
    )
    linhas = calcular_todos_os_indices(parte1, parte2)
    dados = pd.DataFrame(
        [
            {
                "Estágio": linha["rotulo"],
                "Índice (%)": float(linha["indice"]),
                "Índice exibido": formatar_percentual(linha["indice"]),
                "Situação": "≥ 25%" if linha["atingiu"] else "< 25%",
            }
            for linha in linhas
            if linha["indice"] is not None
        ]
    )
    if dados.empty:
        st.info("Não há receita arrecadada para comparar os estágios.")
        return

    ordem = [ESTAGIOS[estagio] for estagio in ESTAGIOS_COMPARACAO]
    maximo = max(30.0, float(dados["Índice (%)"].max()) * 1.15)
    barras = (
        alt.Chart(dados)
        .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
        .encode(
            x=alt.X("Estágio:N", sort=ordem, axis=alt.Axis(labelAngle=0, title=None)),
            y=alt.Y("Índice (%):Q", scale=alt.Scale(domain=[0, maximo])),
            color=alt.Color(
                "Situação:N",
                scale=alt.Scale(domain=["≥ 25%", "< 25%"], range=["#15803d", "#dc2626"]),
                legend=None,
            ),
            tooltip=["Estágio:N", "Índice exibido:N", "Situação:N"],
        )
    )
    rotulos = barras.mark_text(dy=-12, color="#334155").encode(text="Índice exibido:N")
    linha_meta = (
        alt.Chart(pd.DataFrame({"Meta": [25.0]}))
        .mark_rule(color="#0f172a", strokeDash=[6, 5], strokeWidth=2)
        .encode(y="Meta:Q")
    )
    st.altair_chart((barras + rotulos + linha_meta).properties(height=330), width="stretch")
