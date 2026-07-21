"""Dashboard Streamlit do índice constitucional de educação."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import math
from typing import Any

import altair as alt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from indices_constitucionais import (
    ESTAGIOS_DESPESA,
    ROTULOS_ESTAGIOS,
    ErroConsultaFlexvision,
    ErroRegraNegocio,
    ErroSchemaFlexvision,
    ResultadoEducacao,
    formatar_brl,
    formatar_percentual,
)
from indices_constitucionais.dashboard import (
    carregar_resultado_api,
    carregar_resultado_referencia,
    escopo_credenciais_api,
    formatar_percentual_decisorio,
    mensagem_erro_segura,
    montar_view_model,
)
from indices_constitucionais.flexvision import CONSULTA_PARTE1, CONSULTA_PARTE2


FONTE_CSV = "CSV de referência"
FONTE_API = "API Flexvision"
ESTAGIO_POR_ROTULO = {rotulo: chave for chave, rotulo in ROTULOS_ESTAGIOS.items()}
TTL_RESULTADO_API = timedelta(minutes=15)
VERSAO_CONTRATO_API = "educacao-v8-084835-084837-brutos-abcd-fundeb-filtro"
CONSULTAS_API = (CONSULTA_PARTE1, CONSULTA_PARTE2)
ESTAGIOS_COMPARACAO = (
    "despesa_empenhada",
    "despesa_liquidada",
    "despesa_paga",
)


st.set_page_config(
    page_title="Índice Constitucional da Educação",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    _renderizar_cabecalho()
    fonte, exercicio, periodo, estagio = _renderizar_controles()
    resultado = _obter_resultado(fonte, exercicio, periodo)
    if resultado is None:
        return

    view_model = montar_view_model(resultado, estagio)
    _renderizar_contexto(fonte, exercicio, periodo, view_model)
    _renderizar_cards(view_model)
    _renderizar_relogios(view_model)
    _renderizar_comparacao_estagios(view_model)
    _renderizar_detalhamento(resultado, view_model)


def _renderizar_cabecalho() -> None:
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
          <p>Acompanhamento do percentual aplicado sobre a base constitucional de receitas para manutenção e desenvolvimento do ensino.</p>
        </section>
        """
    )


def _renderizar_controles() -> tuple[str, int, int, str]:
    with st.container(border=True):
        coluna_fonte, coluna_exercicio, coluna_periodo, coluna_estagio = st.columns(
            [1.7, 1, 1, 1.7]
        )
        with coluna_fonte:
            fonte = st.radio(
                "Fonte dos dados",
                (FONTE_CSV, FONTE_API),
                horizontal=True,
                help=(
                    "O CSV adaptado é a referência offline com A–D brutos; "
                    "a API busca o período escolhido."
                ),
            )
        modo_api = fonte == FONTE_API
        st.session_state.setdefault("exercicio_flex_educacao", 2026)
        st.session_state.setdefault("periodo_flex_educacao", 4)
        if not modo_api:
            st.session_state["exercicio_flex_educacao"] = 2026
            st.session_state["periodo_flex_educacao"] = 4
        with coluna_exercicio:
            exercicio = int(
                st.number_input(
                    "Exercício",
                    min_value=2020,
                    max_value=2100,
                    step=1,
                    disabled=not modo_api,
                    key="exercicio_flex_educacao",
                )
            )
        with coluna_periodo:
            periodo = int(
                st.selectbox(
                    "Período Flexvision",
                    options=tuple(range(1, 13)),
                    disabled=not modo_api,
                    format_func=lambda valor: f"{valor:02d}",
                    key="periodo_flex_educacao",
                )
            )
        with coluna_estagio:
            rotulo_estagio = st.selectbox(
                "Estágio usado no índice",
                options=tuple(ROTULOS_ESTAGIOS.values()),
                index=tuple(ESTAGIOS_DESPESA).index("despesa_liquidada"),
                help="A escolha do estágio altera o numerador, sem refazer a consulta.",
            )
    return fonte, exercicio, periodo, ESTAGIO_POR_ROTULO[rotulo_estagio]


def _obter_resultado(fonte: str, exercicio: int, periodo: int) -> Any | None:
    fonte_anterior = st.session_state.get("fonte_dashboard_educacao")
    if fonte_anterior is not None and fonte_anterior != fonte:
        _limpar_snapshot_api()
    st.session_state["fonte_dashboard_educacao"] = fonte

    if fonte == FONTE_CSV:
        try:
            return carregar_resultado_referencia()
        except Exception as erro:  # a apresentação transforma em mensagem segura
            _renderizar_erro_carga(erro, fonte)
            return None

    parametros = (exercicio, periodo)
    snapshot = st.session_state.get("snapshot_api_educacao")
    mensagem_reconsulta = None
    if snapshot is not None and not _snapshot_api_estruturalmente_valido(snapshot):
        _limpar_snapshot_api()
        snapshot = None
    if snapshot and snapshot.get("parametros") != parametros:
        _limpar_snapshot_api()
        snapshot = None
    if snapshot and snapshot.get("versao_contrato") != VERSAO_CONTRATO_API:
        _limpar_snapshot_api()
        snapshot = None
    if (
        snapshot
        and datetime.now().astimezone() - snapshot["carregado_em"]
        > TTL_RESULTADO_API
    ):
        _limpar_snapshot_api()
        snapshot = None
        mensagem_reconsulta = (
            "O resultado anterior expirou. Clique em **Consultar / atualizar API** "
            "para obter uma nova posição."
        )
    if snapshot:
        try:
            escopo_atual = escopo_credenciais_api()
        except RuntimeError:
            escopo_atual = None
        if escopo_atual != snapshot.get("escopo_credencial"):
            _limpar_snapshot_api()
            snapshot = None
            mensagem_reconsulta = (
                "As credenciais foram alteradas. Clique em **Consultar / atualizar API** "
                "para obter uma nova posição."
            )

    carregar = st.button("Consultar / atualizar API", type="primary", icon="🔄")
    if carregar:
        try:
            escopo = escopo_credenciais_api()
            with st.spinner(
                f"Consultando {CONSULTA_PARTE1} e {CONSULTA_PARTE2} — "
                f"{exercicio}/{periodo:02d}..."
            ):
                resultado = carregar_resultado_api(exercicio, periodo)
            if not isinstance(resultado, ResultadoEducacao):
                raise ErroSchemaFlexvision(
                    "O pipeline da API não retornou um ResultadoEducacao válido."
                )
            snapshot = {
                "resultado": resultado,
                "parametros": parametros,
                "consultas": CONSULTAS_API,
                "versao_contrato": VERSAO_CONTRATO_API,
                "escopo_credencial": escopo,
                "carregado_em": datetime.now().astimezone(),
            }
            st.session_state["snapshot_api_educacao"] = snapshot
        except Exception as erro:  # não exibe traceback, URL ou resposta integral
            _limpar_snapshot_api()
            _renderizar_erro_carga(erro, fonte)
            return None

    snapshot = st.session_state.get("snapshot_api_educacao")
    if snapshot and snapshot.get("parametros") == parametros:
        return snapshot.get("resultado")

    st.info(
        mensagem_reconsulta
        or (
            "Selecione exercício e período e clique em **Consultar / atualizar API**. "
            "As credenciais são lidas do `.env` e não aparecem na página."
        ),
        icon="ℹ️",
    )
    return None


def _limpar_snapshot_api() -> None:
    st.session_state.pop("snapshot_api_educacao", None)


def _snapshot_api_estruturalmente_valido(snapshot: Any) -> bool:
    carregado_em = snapshot.get("carregado_em") if isinstance(snapshot, dict) else None
    parametros = snapshot.get("parametros") if isinstance(snapshot, dict) else None
    return bool(
        isinstance(snapshot, dict)
        and isinstance(snapshot.get("resultado"), ResultadoEducacao)
        and snapshot.get("consultas") == CONSULTAS_API
        and snapshot.get("versao_contrato") == VERSAO_CONTRATO_API
        and isinstance(parametros, tuple)
        and len(parametros) == 2
        and all(type(valor) is int for valor in parametros)
        and isinstance(snapshot.get("escopo_credencial"), str)
        and isinstance(carregado_em, datetime)
        and carregado_em.tzinfo is not None
    )


def _renderizar_erro_carga(erro: Exception, fonte: str) -> None:
    if isinstance(erro, ErroConsultaFlexvision):
        titulo = f"O Flexvision não conseguiu processar a consulta {erro.consulta_id}."
    elif isinstance(erro, ErroSchemaFlexvision):
        titulo = "A estrutura retornada pelo Flexvision está incompatível."
    elif isinstance(erro, ErroRegraNegocio):
        titulo = "Os dados retornados não reconciliaram com as regras de cálculo."
    elif isinstance(erro, FileNotFoundError):
        titulo = "Os arquivos CSV de referência não foram encontrados."
    elif fonte == FONTE_API and erro.__class__.__name__ == "SiafeAuthenticationError":
        titulo = "Não foi possível autenticar no SIAFE-Rio."
    else:
        titulo = "Não foi possível carregar os dados selecionados."

    st.error(titulo, icon="🚫")
    with st.expander("Ver diagnóstico seguro"):
        # O cifrão isolado é interpretado como delimitador matemático pelo
        # Markdown do Streamlit; escapá-lo mantém mensagens como "R$" legíveis.
        diagnostico = mensagem_erro_segura(erro).replace("$", r"\$")
        st.write(diagnostico)
        if fonte == FONTE_API:
            if (
                isinstance(erro, ErroSchemaFlexvision)
                and "cabeçalhos 'R$' repetidos" in str(erro)
            ):
                st.caption(
                    f"Na {CONSULTA_PARTE1}, substitua os quatro cabeçalhos efetivos "
                    "`R$` por "
                    "aliases únicos: `Receita Prevista`, `Receita Arrecadada`, "
                    "`Diferença (B-A)` e `Arrecadada/Prevista`. A linha amarela "
                    "visual, sozinha, não renomeia as chaves do JSON."
                )
            elif (
                isinstance(erro, ErroSchemaFlexvision)
                and "FUNDEB-FILTRO" in str(erro)
            ):
                st.caption(
                    f"Na {CONSULTA_PARTE2}, deixe o nó "
                    "nó bruto com um título que contenha `FUNDEB` e `FILTRO`, por "
                    "exemplo `INSUMO FUNDEB-FILTRO`, como linha independente no "
                    "JSON. O Python reproduz a expressão do Flexvision calculando "
                    "`0 - valor do filtro` em cada estágio."
                )
            elif (
                isinstance(erro, ErroConsultaFlexvision)
                and erro.consulta_id == CONSULTA_PARTE2
            ):
                st.caption(
                    f"Na {CONSULTA_PARTE2}, remova as expressões consolidadas A–D — "
                    "em especial "
                    "o `SE(...)` da linha B — e mantenha os insumos brutos. A "
                    "linha direta `TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB` ou "
                    "seu insumo `...FUNDEB-FILTRO` precisa chegar no JSON."
                )
            else:
                st.caption(
                    f"Confira os aliases únicos da {CONSULTA_PARTE1} e, na "
                    f"{CONSULTA_PARTE2}, mantenha somente os insumos brutos "
                    "necessários aos cálculos A–D."
                )


def _renderizar_contexto(
    fonte: str, exercicio: int, periodo: int, view_model: dict[str, Any]
) -> None:
    if fonte == FONTE_CSV:
        contexto = "Referência offline • abril/2026 • A–D brutos recalculados"
    else:
        snapshot = st.session_state.get("snapshot_api_educacao", {})
        carregado_em = snapshot.get("carregado_em")
        horario = carregado_em.strftime("%d/%m/%Y %H:%M:%S %z") if carregado_em else "—"
        contexto = (
            f"API Flexvision • {exercicio}/{periodo:02d} • dados brutos recalculados "
            f"• carregado em {horario}"
        )
    st.html(f'<span class="contexto-educacao">{contexto}</span>')
    st.caption(
        f"Situação no estágio **{view_model['rotulo_estagio']}**. "
        "A seleção do estágio é analítica e não constitui conclusão jurídica."
    )
    for aviso in view_model["avisos"]:
        st.warning(aviso, icon="⚠️")


def _renderizar_cards(view_model: dict[str, Any]) -> None:
    colunas = st.columns(4)
    for coluna, card in zip(colunas, view_model["cards"]):
        with coluna:
            st.metric(
                card["rotulo"],
                card["valor"],
                delta=card.get("delta"),
                help=card.get("ajuda"),
                border=True,
                width="stretch",
            )

    situacao = view_model["situacao"]
    mensagem = f"**{situacao['titulo']}** — {situacao['mensagem']}"
    if situacao["tipo"] == "success":
        st.success(mensagem, icon="✅")
    elif situacao["tipo"] == "error":
        st.error(mensagem, icon="📉")
    else:
        st.warning(mensagem, icon="⚠️")


def _renderizar_relogios(view_model: dict[str, Any]) -> None:
    st.subheader("Visão do período e da meta anual prevista", anchor=False)
    st.caption(
        "O relógio do período acompanha o estágio selecionado; a visão anual usa "
        "sempre a despesa liquidada. Ambos mantêm a referência de 25%."
    )
    coluna_periodo, coluna_anual = st.columns(2)

    metricas_periodo = view_model["metricas"]
    with coluna_periodo:
        indice_periodo = metricas_periodo["indice_aplicacao_percentual"]
        if indice_periodo is None:
            st.info("A receita arrecadada é zero; o índice do período está indisponível.")
        else:
            st.plotly_chart(
                _criar_relogio_indice(
                    indice_periodo,
                    titulo="Índice do período",
                    subtitulo=(
                        f"{view_model['rotulo_estagio']} ÷ receita arrecadada"
                    ),
                    neutro=False,
                ),
                width="stretch",
                key="relogio_indice_periodo",
                config={"displayModeBar": False},
            )
            cobertura = formatar_percentual_decisorio(
                metricas_periodo["atingimento_do_minimo_percentual"],
                Decimal("100"),
            )
            st.caption(
                f"Cobertura do mínimo do período: **{cobertura}** — "
                f"{formatar_brl(metricas_periodo['aplicacao_educacao'])} de "
                f"{formatar_brl(metricas_periodo['minimo_constitucional'])}."
            )

    visao_anual = view_model["visao_anual"]
    metricas_anuais = visao_anual["metricas"]
    with coluna_anual:
        indice_previsto = metricas_anuais[
            "indice_sobre_receita_prevista_percentual"
        ]
        if indice_previsto is None:
            st.info("A receita prevista é zero; a visão anual está indisponível.")
        else:
            st.plotly_chart(
                _criar_relogio_indice(
                    indice_previsto,
                    titulo="Índice sobre a previsão anual",
                    subtitulo="Despesa liquidada ÷ receita prevista",
                    neutro=True,
                ),
                width="stretch",
                key="relogio_indice_anual",
                config={"displayModeBar": False},
            )
            st.caption(
                f"Índice sobre a receita prevista: "
                f"**{visao_anual['indice_previsto_formatado']}**. "
                f"Execução da meta anual prevista: "
                f"**{visao_anual['atingimento_meta_formatado']}** — "
                f"{formatar_brl(metricas_anuais['aplicacao_educacao'])} de "
                f"{formatar_brl(metricas_anuais['minimo_constitucional_previsto'])}."
            )

    st.markdown("#### Valores da previsão anual")
    colunas = st.columns(len(visao_anual["cards"]))
    for coluna, card in zip(colunas, visao_anual["cards"]):
        with coluna:
            st.metric(
                card["rotulo"],
                card["valor"],
                help=card.get("ajuda"),
                border=True,
                width="stretch",
            )
    st.caption(
        "A visão anual é gerencial: compara a despesa liquidada acumulada com a "
        "receita prevista do exercício. Ela não substitui a apuração sobre a receita "
        "efetivamente arrecadada."
    )


def _criar_relogio_indice(
    valor: Decimal,
    *,
    titulo: str,
    subtitulo: str,
    neutro: bool,
) -> go.Figure:
    valor_float = max(0.0, float(valor))
    meta = 25.0
    eixo_maximo = max(30.0, math.ceil(max(valor_float, meta) * 1.15 / 5.0) * 5.0)
    atingiu = valor >= Decimal("25")
    cor_barra = "#15803d" if atingiu else ("#0f766e" if neutro else "#dc2626")
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
        "number": {
            "suffix": "%",
            "valueformat": ".2f",
            "font": {"size": 46, "color": cor_barra},
        },
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
            "bar": {"color": cor_barra, "thickness": 0.38},
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


def _renderizar_comparacao_estagios(view_model: dict[str, Any]) -> None:
    st.subheader("Comparação entre estágios", anchor=False)
    st.caption(
        "A linha tracejada representa 25%. O gráfico apresenta somente despesa "
        "empenhada, liquidada e paga."
    )
    linhas_comparacao = [
        linha
        for linha in view_model["linhas_estagios"]
        if linha["estagio"] in ESTAGIOS_COMPARACAO
    ]
    dados = pd.DataFrame(
        [
            {
                "Estágio": linha["rotulo"],
                "Índice (%)": _decimal_para_float(linha["indice_percentual"]),
                "Índice exibido": linha["indice_formatado"],
                "Situação": "≥ 25%" if linha["atingiu_minimo"] else "< 25%",
            }
            for linha in linhas_comparacao
            if linha["indice_percentual"] is not None
        ]
    )
    if dados.empty:
        st.info("Não há base arrecadada para comparar os estágios.")
        return

    ordem = [linha["rotulo"] for linha in linhas_comparacao]
    maximo = max(30.0, float(dados["Índice (%)"].max()) * 1.15)
    barras = (
        alt.Chart(dados)
        .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
        .encode(
            x=alt.X("Estágio:N", sort=ordem, axis=alt.Axis(labelAngle=0, title=None)),
            y=alt.Y("Índice (%):Q", scale=alt.Scale(domain=[0, maximo])),
            color=alt.Color(
                "Situação:N",
                scale=alt.Scale(
                    domain=["≥ 25%", "< 25%"],
                    range=["#15803d", "#dc2626"],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Estágio:N"),
                alt.Tooltip("Índice exibido:N", title="Índice"),
                alt.Tooltip("Situação:N"),
            ],
        )
    )
    rotulos = barras.mark_text(dy=-12, color="#334155").encode(text="Índice exibido:N")
    meta = (
        alt.Chart(pd.DataFrame({"Meta": [25.0]}))
        .mark_rule(color="#0f172a", strokeDash=[6, 5], strokeWidth=2)
        .encode(y="Meta:Q")
    )
    st.altair_chart((barras + rotulos + meta).properties(height=330), width="stretch")


def _renderizar_detalhamento(resultado: Any, view_model: dict[str, Any]) -> None:
    aba_formacao, aba_receita, aba_memoria, aba_dados = st.tabs(
        [
            "Formação da aplicação",
            "Base de receita",
            "Memória A e C",
            "Dados normalizados",
        ]
    )

    with aba_formacao:
        coluna_grafico, coluna_tabela = st.columns([1, 1.45])
        with coluna_grafico:
            st.markdown(f"#### Redutores — {view_model['rotulo_estagio']}")
            dados_redutores = pd.DataFrame(
                [
                    {
                        "Redutor": linha["redutor"],
                        "Valor (R$)": _decimal_para_float(linha["valor"]),
                    }
                    for linha in view_model["linhas_redutores"]
                ]
            )
            grafico = (
                alt.Chart(dados_redutores)
                .mark_bar(color="#c2410c", cornerRadiusEnd=5)
                .encode(
                    y=alt.Y("Redutor:N", sort=None, title=None),
                    x=alt.X("Valor (R$):Q", title="Valor redutor (R$)"),
                    tooltip=[
                        alt.Tooltip("Redutor:N"),
                        alt.Tooltip("Valor (R$):Q", format=",.2f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(grafico, width="stretch")
        with coluna_tabela:
            st.markdown("#### Quadro completo por estágio")
            st.dataframe(
                pd.DataFrame(view_model["quadro_resumo"]),
                hide_index=True,
                width="stretch",
            )

    with aba_receita:
        receita_1, receita_2, receita_3 = st.columns(3)
        metricas = view_model["metricas"]
        receita_1.metric(
            "Receita prevista",
            formatar_brl(metricas["receita_prevista"]),
            border=True,
        )
        receita_2.metric(
            "Receita arrecadada",
            formatar_brl(metricas["receita_arrecadada"]),
            border=True,
        )
        receita_3.metric(
            "Arrecadada / prevista",
            formatar_percentual(metricas["realizacao_receita_percentual"]),
            border=True,
        )
        st.dataframe(
            pd.DataFrame(view_model["componentes_receita"]),
            hide_index=True,
            width="stretch",
        )

    with aba_memoria:
        st.markdown("#### Redutor A — abertura por grupo")
        if view_model["detalhes_a"]:
            st.dataframe(
                pd.DataFrame(view_model["detalhes_a"]), hide_index=True, width="stretch"
            )
        else:
            st.info(
                "A fonte carregada não contém a abertura bruta do A por impostos e "
                "complementação da União."
            )

        st.markdown("#### Redutor C — abertura por exercício")
        if view_model["detalhes_c"]:
            st.dataframe(
                pd.DataFrame(view_model["detalhes_c"]), hide_index=True, width="stretch"
            )
        else:
            st.info(
                "A fonte carregada não contém os pares anuais brutos de RP cancelado "
                "e excesso aplicado usados no cálculo do C."
            )

    with aba_dados:
        st.caption(
            "Resultado da Parte 2 após aplicar as regras A–D, no mesmo desenho "
            "lógico do relatório consolidado antigo."
        )
        st.dataframe(
            pd.DataFrame(view_model["relatorio_calculado"]),
            hide_index=True,
            width="stretch",
        )

        with st.expander("Ver insumos brutos normalizados"):
            st.caption(
                "Estas são as linhas recebidas antes da consolidação. Elas são "
                "mantidas para rastrear os cálculos de A, B, C e D."
            )
            linhas = []
            for linha in resultado.parte2.linhas_normalizadas:
                linhas.append(
                    {
                        "Descrição": linha["descricao"],
                        **{
                            ROTULOS_ESTAGIOS[estagio]: formatar_brl(linha[estagio])
                            for estagio in ESTAGIOS_DESPESA
                        },
                    }
                )
            st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")


def _decimal_para_float(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


if __name__ == "__main__":
    main()
