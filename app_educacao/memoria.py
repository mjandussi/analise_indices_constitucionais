"""Memórias de cálculo e tabelas de auditoria do índice."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app_educacao.apresentacao import (
    formula_monetaria,
    linha_financeira,
    quadro_formacao_aplicacao,
    relatorio_calculado,
)
from app_educacao.config import CONSULTA_DESPESAS, CONSULTA_RECEITAS, ESTAGIOS
from app_educacao.dados import formatar_brl, formatar_percentual


def renderizar_memoria(
    parte1: dict[str, Any],
    parte2: dict[str, Any],
    metricas: dict[str, Any],
    estagio: str,
) -> None:
    """Abre fórmulas, insumos e linhagem para explicação e auditoria."""

    st.subheader("Memória de cálculo para apresentação à equipe", anchor=False)
    st.caption(
        "As tabelas abaixo usam os mesmos Decimals do resultado. A formatação ocorre "
        "somente depois dos cálculos."
    )
    aba_geral, aba_abcd, aba_receitas, aba_api = st.tabs(
        [
            "Fórmula principal e métricas",
            "Regras A–D",
            "Base de receitas",
            "Rastreabilidade da API",
        ]
    )

    # Aba 1: explica como os números finais se conectam. É a melhor porta de
    # entrada para quem quer apresentar o resultado sem abrir cada insumo.
    with aba_geral:
        st.markdown(f"#### Formação da aplicação — {ESTAGIOS[estagio]}")
        st.markdown(
            "**Aplicação = valores positivos − A − B − C − D − outras deduções**"
        )
        st.code(formula_monetaria(parte2, estagio), language=None)
        st.dataframe(
            pd.DataFrame(quadro_formacao_aplicacao(parte2)),
            hide_index=True,
            width="stretch",
        )

        st.markdown("#### Como a aplicação vira índice")
        st.code(
            f"Mínimo do período = {formatar_brl(parte1['base_arrecadada'])} × 25% "
            f"= {formatar_brl(parte1['minimo_arrecadado'])}\n"
            f"Índice do período = {formatar_brl(metricas['aplicado'])} ÷ "
            f"{formatar_brl(parte1['base_arrecadada'])} × 100 "
            f"= {formatar_percentual(metricas['indice_periodo'])}",
            language=None,
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Métrica": "Índice do período",
                        "Fórmula": "Aplicação do estágio ÷ receita arrecadada × 100",
                        "Resultado": formatar_percentual(metricas["indice_periodo"]),
                    },
                    {
                        "Métrica": "Cobertura do mínimo",
                        "Fórmula": "Aplicação do estágio ÷ mínimo do período × 100",
                        "Resultado": formatar_percentual(metricas["cobertura_minimo"]),
                    },
                    {
                        "Métrica": "Índice sobre a previsão anual",
                        "Fórmula": "Despesa liquidada ÷ receita prevista × 100",
                        "Resultado": formatar_percentual(metricas["indice_anual"]),
                    },
                    {
                        "Métrica": "Execução da meta anual",
                        "Fórmula": "Despesa liquidada ÷ (25% da receita prevista) × 100",
                        "Resultado": formatar_percentual(metricas["execucao_meta_anual"]),
                    },
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    # Aba 2: abre cada regra, permitindo conferir exatamente qual dado bruto
    # gerou o redutor mostrado na fórmula principal.
    with aba_abcd:
        st.markdown("#### Redutor A — superávit do exercício anterior")
        st.markdown(
            "Para cada grupo: **máximo entre (superávit financeiro − aplicação do "
            "superávit) e zero**. Depois, os dois grupos são somados."
        )
        tabela_a = []
        for detalhe in parte2["detalhes_a"]:
            tabela_a.append(
                {
                    "Grupo": detalhe["grupo"],
                    "Superávit financeiro": formatar_brl(detalhe["superavit"][estagio]),
                    "Aplicação do superávit": formatar_brl(detalhe["aplicacao"][estagio]),
                    "Redutor A": formatar_brl(detalhe["redutor"][estagio]),
                }
            )
        st.dataframe(pd.DataFrame(tabela_a), hide_index=True, width="stretch")

        st.markdown("#### Redutor B — FUNDEB não utilizado acima de 10%")
        st.markdown(
            "**B = máximo entre [receita recebida − despesa custeada − "
            "10% da receita recebida] e zero.** A receita recebida é insumo do B; "
            "não é a linha positiva de receitas transferidas ao FUNDEB."
        )
        detalhe_b = parte2["detalhes_b"]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Estágio": ESTAGIOS[estagio],
                        "Receita FUNDEB": formatar_brl(detalhe_b["receita_fundeb"][estagio]),
                        "Despesa FUNDEB": formatar_brl(detalhe_b["despesa_fundeb"][estagio]),
                        "Valor não aplicado": formatar_brl(
                            detalhe_b["valor_nao_aplicado"][estagio]
                        ),
                        "Limite de 10%": formatar_brl(
                            detalhe_b["limite_dez_por_cento"][estagio]
                        ),
                        "Redutor B": formatar_brl(detalhe_b["redutor"][estagio]),
                    }
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        st.markdown("#### Redutor C — RP cancelados da MDE")
        st.markdown(
            "**RP** significa Restos a Pagar e **MDE**, Manutenção e Desenvolvimento "
            "do Ensino. "
            "Para cada ano: **máximo entre (RP cancelado − excesso já aplicado) e "
            "zero**. O redutor C é a soma dos resultados anuais."
        )
        tabela_c = [
            {
                "Ano": detalhe["ano"],
                "RP cancelado": formatar_brl(detalhe["rp_cancelado"][estagio]),
                "Excesso aplicado": formatar_brl(detalhe["excesso_aplicado"][estagio]),
                "Redutor C": formatar_brl(detalhe["redutor"][estagio]),
            }
            for detalhe in parte2["detalhes_c"]
        ]
        st.dataframe(pd.DataFrame(tabela_c), hide_index=True, width="stretch")

        st.markdown("#### Redutor D — Restos a Pagar Cancelados do TAC")
        st.markdown(
            "**TAC** significa Termo de Ajustamento de Conduta. "
            "**D = somatório das linhas anuais identificadas como RP Cancelado TAC.**"
        )
        tabela_d = [
            {
                "Ano": detalhe["ano"],
                ESTAGIOS[estagio]: formatar_brl(detalhe["valores"][estagio]),
            }
            for detalhe in parte2["detalhes_d"]
        ]
        st.dataframe(pd.DataFrame(tabela_d), hide_index=True, width="stretch")

        st.markdown("#### Resumo dos redutores em todos os estágios")
        st.dataframe(
            pd.DataFrame(quadro_formacao_aplicacao(parte2)[1:6]),
            hide_index=True,
            width="stretch",
        )

    # Aba 3: mostra o denominador. Ela ajuda a separar realização da receita do
    # índice constitucional, que depende também da aplicação em educação.
    with aba_receitas:
        st.markdown("#### Parte 1 — componentes da base constitucional")
        st.markdown(
            "As linhas (+) e (−) são somadas com o sinal recebido da consulta. "
            "Não usamos as linhas visuais de cabeçalho. Arrecadada/prevista mede "
            "a realização da receita; não é o índice constitucional da educação."
        )
        componentes = [
            {
                "Componente": item["descricao"],
                "Receita prevista": formatar_brl(item["receita_prevista"]),
                "Receita arrecadada": formatar_brl(item["receita_arrecadada"]),
            }
            for item in parte1["componentes"]
        ]
        componentes.append(
            {
                "Componente": "TOTAL — BASE DE CÁLCULO RECOMPOSTA",
                "Receita prevista": formatar_brl(parte1["base_prevista"]),
                "Receita arrecadada": formatar_brl(parte1["base_arrecadada"]),
            }
        )
        st.dataframe(pd.DataFrame(componentes), hide_index=True, width="stretch")
        col1, col2, col3 = st.columns(3)
        col1.metric("Base prevista", formatar_brl(parte1["base_prevista"]), border=True)
        col2.metric("Base arrecadada", formatar_brl(parte1["base_arrecadada"]), border=True)
        col3.metric(
            "Arrecadada / prevista",
            formatar_percentual(parte1["realizacao_percentual"]),
            border=True,
        )

    # Aba 4: rastreabilidade. "Normalizar" aqui significa converter números para
    # Decimal e títulos para comparação segura, sem criar valores ausentes.
    with aba_api:
        st.markdown("#### Linhagem dos dados")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Parte": "1 — receitas",
                        "Consulta": CONSULTA_RECEITAS,
                        "O que fornece": "Receitas prevista e arrecadada",
                        "Tratamento": "Soma dos componentes e cálculo de 25%",
                    },
                    {
                        "Parte": "2 — aplicação",
                        "Consulta": CONSULTA_DESPESAS,
                        "O que fornece": "Despesas e insumos brutos A–D",
                        "Tratamento": "Cálculos A–D e total aplicado por estágio",
                    },
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.info(
            "Total transferido ao FUNDEB: "
            f"**{parte2['origem_total_fundeb']}**. O nó técnico não é contado duas vezes.",
            icon="🔎",
        )
        st.markdown("#### Relatório após os cálculos")
        st.dataframe(
            pd.DataFrame(relatorio_calculado(parte2)),
            hide_index=True,
            width="stretch",
        )
        with st.expander(
            f"Ver todas as linhas brutas normalizadas da consulta {CONSULTA_DESPESAS}"
        ):
            linhas_brutas = [
                linha_financeira(linha["descricao"], linha["valores"])
                for linha in parte2["linhas_brutas"]
            ]
            st.dataframe(pd.DataFrame(linhas_brutas), hide_index=True, width="stretch")
