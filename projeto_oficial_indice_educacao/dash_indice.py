"""Dashboard do índice constitucional atual da Educação.

Execute com: ``streamlit run dash_indice.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
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


def exibir_comparacao(parte1: dict[str, Any], parte2: dict[str, Any]) -> None:
    """Compara os três estágios usados no acompanhamento."""

    linhas = calcular_todos_os_indices(parte1, parte2)
    grafico = pd.DataFrame(
        {
            "Estágio": [linha["Estágio"] for linha in linhas],
            "Índice (%)": [float(linha["Índice (%)"] or 0) for linha in linhas],
        }
    ).set_index("Estágio")
    st.subheader("Comparação por estágio")
    st.bar_chart(grafico, horizontal=True)
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
    exibir_comparacao(parte1, parte2)
    exibir_memoria(parte1, parte2, estagio)

    st.caption(
        f"Meta de referência: {formatar_percentual(META_CONSTITUCIONAL)}. "
        "A interpretação jurídica permanece a cargo da área responsável."
    )


if __name__ == "__main__":
    main()
