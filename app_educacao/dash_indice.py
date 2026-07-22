"""Dashboard principal do índice constitucional da educação."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from app_educacao.apresentacao import diagnostico_seguro
from app_educacao.config import (
    CONSULTA_DESPESAS,
    CONSULTA_RECEITAS,
    ESTAGIOS,
    VERSAO_CALCULO,
)
from app_educacao.dados import calcular_metricas, processar_snapshot
from app_educacao.dash_projecao import renderizar_projecao
from app_educacao.extracao import extrair_e_persistir_dados_educacao, localizar_snapshot
from app_educacao.graficos import (
    renderizar_cards,
    renderizar_comparacao,
    renderizar_relogios,
)
from app_educacao.memoria import renderizar_memoria


def renderizar_cabecalho() -> None:
    """Desenha o título e o estilo visual comum da página."""

    st.html(
        """
        <style>
          .hero-educacao {
            padding: 1.45rem 1.65rem;
            border-radius: 18px;
            color: white;
            background: linear-gradient(120deg, #075985 0%, #0f766e 58%, #15803d 100%);
            margin-bottom: 1rem;
            box-shadow: 0 10px 28px rgba(15, 118, 110, .16);
          }
          .hero-educacao h1 { margin: 0; font-size: 2rem; line-height: 1.2; }
          .hero-educacao p { margin: .45rem 0 0; opacity: .92; font-size: 1rem; }
          .contexto-educacao {
            display: inline-block;
            padding: .32rem .72rem;
            border-radius: 999px;
            background: #e6fffb;
            color: #115e59;
            font-weight: 600;
            margin-bottom: .45rem;
          }
        </style>
        <section class="hero-educacao">
          <h1>Índice Constitucional da Educação</h1>
          <p>Extração do Flexvision para CSV, ETL dos dados brutos e memória completa do mínimo de 25%.</p>
        </section>
        """
    )


def renderizar_metodologia_inicial() -> None:
    """Mostra um resumo do pipeline antes mesmo de haver uma consulta."""

    with st.expander("Entenda o fluxo dos dados e do cálculo", expanded=False):
        st.markdown(
            f"""
1. `extracao.py` consulta **{CONSULTA_RECEITAS}** e **{CONSULTA_DESPESAS}** e grava `parte1.csv` e `parte2.csv`.
2. `dados.py` lê esses dois CSVs, preservando as células financeiras como texto até convertê-las para `Decimal`.
3. A Parte 1 recompõe a receita e calcula **25% da receita arrecadada**.
4. A Parte 2 calcula os redutores **A, B, C e D** para cada estágio.
5. A aplicação é: **valores positivos − A − B − C − D − outras deduções**.
6. O índice é: **aplicação do estágio ÷ receita arrecadada × 100**.
"""
        )
        st.info(
            "Na Parte 1, a transferência aos municípios já chega negativa. Na Parte 2, "
            "as deduções chegam como valores positivos e são subtraídas pelo Python. "
            "A única exceção é o nó técnico FUNDEB-FILTRO, invertido por 0 − filtro.",
            icon="ℹ️",
        )


def renderizar_controles() -> tuple[int, int, str]:
    """Coleta ano, período e estágio; ainda não chama a API."""

    with st.container(border=True):
        coluna_ano, coluna_periodo, coluna_estagio = st.columns([1, 1, 1.7])
        with coluna_ano:
            exercicio = int(
                st.number_input(
                    "Exercício",
                    min_value=2020,
                    max_value=2100,
                    value=2026,
                    step=1,
                    key="app_edu_exercicio",
                    help="Primeiro parâmetro enviado às duas consultas Flexvision.",
                )
            )
        with coluna_periodo:
            periodo = int(
                st.selectbox(
                    "Período Flexvision",
                    options=tuple(range(1, 13)),
                    index=3,
                    format_func=lambda valor: f"{valor:02d}",
                    key="app_edu_periodo",
                    help="Segundo parâmetro enviado às duas consultas Flexvision.",
                )
            )
        with coluna_estagio:
            estagio = st.selectbox(
                "Estágio usado no índice",
                options=tuple(ESTAGIOS),
                index=tuple(ESTAGIOS).index("despesa_liquidada"),
                format_func=lambda chave: ESTAGIOS[chave],
                key="app_edu_estagio",
                help=(
                    "Trocar o estágio muda somente a análise. Os dados já carregados "
                    "não são consultados novamente."
                ),
            )
    return exercicio, periodo, estagio


def obter_resultado(exercicio: int, periodo: int) -> dict[str, Any] | None:
    """Extrai os JSONs, publica os CSVs e executa a ETL desses arquivos."""

    chave_atual = (
        exercicio,
        periodo,
        CONSULTA_RECEITAS,
        CONSULTA_DESPESAS,
        VERSAO_CALCULO,
    )
    consultar = st.button("Consultar / atualizar API", type="primary", icon="🔄")

    if consultar:
        st.session_state.pop("app_edu_resultado", None)
        try:
            with st.spinner(
                f"Extraindo {CONSULTA_RECEITAS} e {CONSULTA_DESPESAS}, "
                "gerando os CSVs e calculando o índice..."
            ):
                _, pasta_snapshot = extrair_e_persistir_dados_educacao(
                    exercicio,
                    periodo,
                )
                resultado = processar_snapshot(pasta_snapshot)
            resultado.update(
                {
                    "chave": chave_atual,
                    "carregado_em": datetime.now().astimezone(),
                }
            )
            st.session_state["app_edu_resultado"] = resultado
        except Exception as erro:
            st.error("Não foi possível extrair e calcular o índice.", icon="🚫")
            with st.expander("Ver diagnóstico seguro"):
                st.write(diagnostico_seguro(erro).replace("$", r"\$"))
            return None

    resultado = st.session_state.get("app_edu_resultado")
    if isinstance(resultado, dict) and resultado.get("chave") == chave_atual:
        return resultado

    # Um CSV já extraído pode ser analisado novamente sem chamar a API.
    try:
        pasta_snapshot = localizar_snapshot(exercicio, periodo)
    except FileNotFoundError:
        st.info(
            "Clique em **Consultar / atualizar API** para gerar os dois CSVs. "
            "Depois disso, filtros e novas análises reutilizam os arquivos locais.",
            icon="ℹ️",
        )
        return None

    try:
        resultado = processar_snapshot(pasta_snapshot)
        resultado.update(
            {
                "chave": chave_atual,
                "carregado_em": datetime.fromtimestamp(
                    pasta_snapshot.stat().st_mtime
                ).astimezone(),
            }
        )
        st.session_state["app_edu_resultado"] = resultado
        return resultado
    except Exception as erro:
        st.error("Os CSVs existentes não puderam ser processados.", icon="🚫")
        with st.expander("Ver diagnóstico seguro"):
            st.write(diagnostico_seguro(erro).replace("$", r"\$"))
        return None



def renderizar_contexto(
    resultado: dict[str, Any], exercicio: int, periodo: int, estagio: str
) -> None:
    """Exibe a referência temporal, IDs usados e ressalva de interpretação."""

    horario = resultado["carregado_em"].strftime("%d/%m/%Y %H:%M:%S %z")
    st.html(
        '<span class="contexto-educacao">'
        f"CSV extraído do Flexvision • {exercicio}/{periodo:02d} • consultas "
        f"{CONSULTA_RECEITAS} + {CONSULTA_DESPESAS} • carregado em {horario}"
        "</span>"
    )
    st.caption(
        f"Situação no estágio **{ESTAGIOS[estagio]}**. A escolha do estágio é "
        "analítica e não constitui conclusão jurídica."
    )
    for aviso in resultado["parte1"]["avisos"]:
        st.warning(aviso, icon="⚠️")


def main(*, incluir_projecao: bool = False) -> None:
    """Orquestra extração, ETL e o dashboard do índice atual."""

    st.set_page_config(
        page_title="Índice Constitucional da Educação",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    renderizar_cabecalho()
    renderizar_metodologia_inicial()
    exercicio, periodo, estagio = renderizar_controles()
    resultado = obter_resultado(exercicio, periodo)
    if resultado is None:
        return

    parte1 = resultado["parte1"]
    parte2 = resultado["parte2"]
    metricas = calcular_metricas(parte1, parte2, estagio)

    renderizar_contexto(resultado, exercicio, periodo, estagio)
    renderizar_cards(metricas, estagio)
    renderizar_relogios(metricas, estagio)
    renderizar_comparacao(parte1, parte2)
    renderizar_memoria(parte1, parte2, metricas, estagio)
    if incluir_projecao:
        renderizar_projecao(parte1, parte2, exercicio, periodo)


if __name__ == "__main__":
    main()
