"""Regras de negócio do índice constitucional de educação."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from .erros import ErroRegraNegocio, ErroSchemaFlexvision
from .modelos import ESTAGIOS_DESPESA, ResultadoEducacao, ResultadoParte1, ResultadoParte2
from .normalizacao import (
    CENTAVO,
    ZERO,
    colunas_disponiveis,
    extrair_registros,
    normalizar_texto,
    numero_decimal,
    quantizar_minimo_constitucional,
    quantizar_moeda,
)


ALIASES_PARTE1 = {
    "prevista": ("RECEITA PREVISTA",),
    "arrecadada": ("RECEITA ARRECADADA",),
    "diferenca": ("DIFERENCA (B-A)", "DIFERENCA B-A", "DIFERENCA"),
    "percentual": ("ARRECADADA/PREVISTA", "ARRECADADA PREVISTA", "B/A"),
}

ALIASES_ESTAGIOS = {
    "dotacao_atual": ("DOTACAO ATUAL",),
    "despesa_autorizada": ("DESPESA AUTORIZADA",),
    "despesa_empenhada": ("DESPESA EMPENHADA",),
    "despesa_liquidada": ("DESPESA LIQUIDADA",),
    "despesa_paga": ("DESPESA PAGA",),
}

GRUPOS_SUPERAVIT = ("impostos", "complementacao_uniao")


def calcular_parte1(
    dados: Any,
    *,
    colunas: Mapping[str, str] | None = None,
    validar_totais: bool = True,
) -> ResultadoParte1:
    """Calcula base de receita e mínimo de 25% da consulta da Parte 1.

    As linhas visuais ``R$`` e ``(A)/(B)/(C)/(B/A)`` são ignoradas. Para o
    JSON, os cabeçalhos efetivos precisam ser únicos: descrição, Receita
    Prevista, Receita Arrecadada, Diferença e Arrecadada/Prevista. Diferença
    e percentual são derivados novamente e, portanto, são opcionais.
    """

    registros = extrair_registros(dados)
    if not registros:
        raise ErroSchemaFlexvision("A consulta da Parte 1 não retornou registros.")

    disponiveis = colunas_disponiveis(registros)
    overrides = dict(colunas or {})
    coluna_descricao = _resolver_coluna_descricao(
        registros,
        overrides.get("descricao"),
        termos_linha=("TOTAL - BASE DE CALCULO",),
        nome_parte="Parte 1",
    )
    # Algumas exportações preservam as colunas como R$, R$_1... e trazem os
    # nomes úteis na linha amarela. Quando as posições ainda existem, essa
    # linha é usada apenas para mapear os cabeçalhos e depois é descartada.
    cabecalho_amarelo = _mapear_linha_cabecalho_parte1(registros, coluna_descricao)

    try:
        coluna_prevista = _resolver_coluna(
            disponiveis,
            "prevista",
            ALIASES_PARTE1["prevista"],
            overrides.get("prevista") or cabecalho_amarelo.get("prevista"),
            aceitar_contem=True,
        )
        coluna_arrecadada = _resolver_coluna(
            disponiveis,
            "arrecadada",
            ALIASES_PARTE1["arrecadada"],
            overrides.get("arrecadada") or cabecalho_amarelo.get("arrecadada"),
            aceitar_contem=True,
        )
    except ErroSchemaFlexvision as erro:
        nomes_norm = {normalizar_texto(nome) for nome in disponiveis}
        if "R$" in nomes_norm:
            raise ErroSchemaFlexvision(
                "A consulta da Parte 1 chegou com cabeçalhos 'R$' repetidos. No payload "
                "observado, restaram somente a descrição e a última chave 'R$', "
                "correspondente a Arrecadada/Prevista. Receita Prevista e Receita "
                "Arrecadada não chegaram e não podem ser inferidas com segurança. "
                "No Flexvision, use como aliases/cabeçalhos efetivos os nomes da "
                "linha amarela: Receita Prevista, Receita Arrecadada, Diferença "
                "(B-A) e Arrecadada/Prevista."
            ) from erro
        raise

    coluna_diferenca = _resolver_coluna_opcional(
        disponiveis,
        ALIASES_PARTE1["diferenca"],
        overrides.get("diferenca") or cabecalho_amarelo.get("diferenca"),
        aceitar_contem=True,
    )
    coluna_percentual = _resolver_coluna_opcional(
        disponiveis,
        ALIASES_PARTE1["percentual"],
        overrides.get("percentual") or cabecalho_amarelo.get("percentual"),
        aceitar_contem=True,
    )

    componentes: list[dict[str, Any]] = []
    total_informado: dict[str, Any] | None = None
    minimo_informado: dict[str, Any] | None = None
    fundeb_informado: dict[str, Any] | None = None

    for indice, registro in enumerate(registros):
        if coluna_descricao not in registro:
            raise ErroSchemaFlexvision(
                f"A linha {indice} da Parte 1 não possui a coluna de descrição "
                f"obrigatória {coluna_descricao!r}."
            )
        valor_descricao = registro[coluna_descricao]
        descricao = "" if valor_descricao is None else str(valor_descricao).strip()
        chave = normalizar_texto(descricao)
        if not chave or chave == "SEPARADOR":
            continue
        if chave.startswith("TOTAL - BASE DE CALCULO"):
            total_informado = registro
            continue
        if "VALOR A SER APLICADO EM EDUCACAO" in chave:
            minimo_informado = registro
            continue
        if "TOTAL DESTINADO AO FUNDEB" in chave:
            fundeb_informado = registro
            continue
        if not (chave.startswith("(+)") or chave.startswith("(-)")):
            continue

        prevista = _ler_decimal(registro, coluna_prevista, indice, descricao)
        arrecadada = _ler_decimal(registro, coluna_arrecadada, indice, descricao)
        if chave.startswith("(-)") and (prevista > ZERO or arrecadada > ZERO):
            raise ErroRegraNegocio(
                f"A linha redutora {descricao!r} da Parte 1 deve chegar com valores "
                "negativos. O sinal já faz parte da receita e não será invertido pelo código."
            )
        componentes.append(
            {
                "descricao": descricao,
                "receita_prevista": prevista,
                "receita_arrecadada": arrecadada,
            }
        )

    if not componentes:
        raise ErroSchemaFlexvision(
            "Nenhum componente de receita '(+)' ou '(-)' foi encontrado na Parte 1."
        )

    base_prevista = quantizar_moeda(
        sum((item["receita_prevista"] for item in componentes), ZERO)
    )
    base_arrecadada = quantizar_moeda(
        sum((item["receita_arrecadada"] for item in componentes), ZERO)
    )
    diferenca = quantizar_moeda(base_arrecadada - base_prevista)
    realizacao = (
        base_arrecadada * Decimal("100") / base_prevista if base_prevista else None
    )
    minimo_prevista = quantizar_minimo_constitucional(base_prevista * Decimal("0.25"))
    minimo_arrecadada = quantizar_minimo_constitucional(
        base_arrecadada * Decimal("0.25")
    )
    diferenca_minimo = quantizar_moeda(minimo_arrecadada - minimo_prevista)

    avisos: list[str] = []
    if validar_totais and total_informado is not None:
        _validar_valor_informado(
            total_informado,
            coluna_prevista,
            base_prevista,
            "base prevista da Parte 1",
        )
        _validar_valor_informado(
            total_informado,
            coluna_arrecadada,
            base_arrecadada,
            "base arrecadada da Parte 1",
        )
        if coluna_diferenca:
            _validar_valor_informado(
                total_informado,
                coluna_diferenca,
                diferenca,
                "diferença de receita da Parte 1",
            )
        if coluna_percentual and realizacao is not None:
            _validar_percentual_informado(
                total_informado,
                coluna_percentual,
                realizacao,
                "realização da receita da Parte 1",
            )
    elif total_informado is None:
        avisos.append("A linha TOTAL - BASE DE CÁLCULO não veio no retorno; o total foi recomposto.")

    if validar_totais and minimo_informado is not None:
        _validar_valor_informado(
            minimo_informado,
            coluna_prevista,
            minimo_prevista,
            "mínimo de 25% sobre a receita prevista",
        )
        _validar_valor_informado(
            minimo_informado,
            coluna_arrecadada,
            minimo_arrecadada,
            "mínimo de 25% sobre a receita arrecadada",
        )

    fundeb_previsto: Decimal | None = None
    fundeb_realizado: Decimal | None = None
    if fundeb_informado is not None:
        fundeb_previsto = quantizar_moeda(
            _ler_decimal(
                fundeb_informado,
                coluna_prevista,
                -1,
                "TOTAL DESTINADO AO FUNDEB",
            )
        )
        fundeb_realizado = quantizar_moeda(
            _ler_decimal(
                fundeb_informado,
                coluna_arrecadada,
                -1,
                "TOTAL DESTINADO AO FUNDEB",
            )
        )
        if fundeb_previsto < ZERO or fundeb_realizado < ZERO:
            raise ErroRegraNegocio(
                "O total destinado ao FUNDEB da Parte 1 não pode ser negativo."
            )

    return ResultadoParte1(
        base_prevista=base_prevista,
        base_arrecadada=base_arrecadada,
        diferenca_receita=diferenca,
        realizacao_percentual=realizacao,
        minimo_sobre_prevista=minimo_prevista,
        minimo_sobre_arrecadada=minimo_arrecadada,
        diferenca_minimo=diferenca_minimo,
        componentes=tuple(componentes),
        avisos=tuple(avisos),
        fundeb_previsto=fundeb_previsto,
        fundeb_realizado=fundeb_realizado,
    )


def calcular_parte2(
    dados: Any,
    *,
    colunas: Mapping[str, str] | None = None,
    validar_total_final: bool = True,
    aceitar_consolidados: bool = False,
) -> ResultadoParte2:
    """Calcula aplicação efetiva e redutores A–D da consulta da Parte 2.

    C e D são classificados pelo significado da descrição, não pela letra
    inicial, pois os prefixos da consulta bruta estão invertidos em relação ao
    documento da regra.
    """

    registros = extrair_registros(dados)
    if not registros:
        raise ErroSchemaFlexvision("A consulta da Parte 2 não retornou registros.")

    disponiveis = colunas_disponiveis(registros)
    overrides = dict(colunas or {})
    coluna_descricao = _resolver_coluna_descricao(
        registros,
        overrides.get("descricao"),
        termos_linha=("FONTE 100", "RECEITAS RECEBIDAS DO FUNDEB"),
        nome_parte="Parte 2",
    )
    colunas_estagios = {
        estagio: _resolver_coluna(
            disponiveis,
            estagio,
            ALIASES_ESTAGIOS[estagio],
            overrides.get(estagio),
            aceitar_contem=False,
        )
        for estagio in ESTAGIOS_DESPESA
    }

    linhas: list[dict[str, Any]] = []
    for indice, registro in enumerate(registros):
        if coluna_descricao not in registro:
            raise ErroSchemaFlexvision(
                f"A linha {indice} da Parte 2 não possui a coluna de descrição "
                f"obrigatória {coluna_descricao!r}."
            )
        valor_descricao = registro[coluna_descricao]
        descricao = "" if valor_descricao is None else str(valor_descricao).strip()
        if not descricao:
            continue
        linha = {
            "indice": indice,
            "descricao": descricao,
            "chave": normalizar_texto(descricao),
            "valores": {
                estagio: _ler_decimal(registro, coluna, indice, descricao)
                for estagio, coluna in colunas_estagios.items()
            },
        }
        linhas.append(linha)

    linhas_recebidas = list(linhas)
    total_transferido_fundeb = _linha_unica(
        linhas,
        lambda chave: (
            "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB" in chave
            and "FILTRO" not in chave
        ),
        "total direto das receitas transferidas ao FUNDEB",
        obrigatoria=False,
    )
    insumo_transferido_fundeb = _linha_unica(
        linhas,
        lambda chave: (
            "FUNDEB" in chave and "FILTRO" in chave
        ),
        "insumo FUNDEB-FILTRO",
        obrigatoria=False,
    )

    total_fundeb_calculado: dict[str, Any] | None = None
    if insumo_transferido_fundeb is not None:
        total_fundeb_calculado = _calcular_total_fundeb_do_filtro(
            insumo_transferido_fundeb
        )

    if total_transferido_fundeb is None and total_fundeb_calculado is None:
        raise ErroSchemaFlexvision(
            "A consulta da Parte 2 não retornou nem a linha positiva TOTAL DAS RECEITAS "
            "TRANSFERIDAS AO FUNDEB nem um insumo cujo título contenha FUNDEB e "
            "FILTRO. O código aceita o total direto ou calcula, por estágio, 0 "
            "menos o valor do insumo -FILTRO."
        )
    if (
        total_transferido_fundeb is not None
        and not total_transferido_fundeb["chave"].startswith("(+)")
    ):
        raise ErroSchemaFlexvision(
            "A linha TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB deve chegar "
            "identificada explicitamente como positiva '(+)'."
        )
    if total_transferido_fundeb is not None:
        _validar_linhas_nao_negativas(
            (total_transferido_fundeb,),
            "total das receitas transferidas ao FUNDEB",
        )
        if total_fundeb_calculado is not None:
            for estagio in ESTAGIOS_DESPESA:
                _comparar_decimal(
                    total_transferido_fundeb["valores"][estagio],
                    total_fundeb_calculado["valores"][estagio],
                    f"total transferido ao FUNDEB em {estagio}",
                )

    # O nó ``-FILTRO`` é um insumo com sinal contábil negativo. Ele não pode
    # participar diretamente da soma das linhas ``(+)``. Quando o total direto
    # não vem no JSON, inserimos sua versão positiva calculada por ``0 - filtro``.
    linhas = [
        linha for linha in linhas if linha is not insumo_transferido_fundeb
    ]
    if total_transferido_fundeb is None and total_fundeb_calculado is not None:
        linhas.append(total_fundeb_calculado)

    positivas = [linha for linha in linhas if linha["chave"].startswith("(+)")]
    if not positivas:
        raise ErroSchemaFlexvision(
            "Nenhuma fonte positiva '(+)' foi encontrada na Parte 2."
        )
    valores_positivos = _somar_linhas(positivas)

    redutor_a, detalhes_a = _calcular_redutor_a(linhas, aceitar_consolidados)
    redutor_b, detalhes_b = _calcular_redutor_b(linhas, aceitar_consolidados)
    redutor_c, detalhes_c = _calcular_redutor_c(linhas, aceitar_consolidados)
    redutor_d, detalhes_d = _calcular_redutor_d(linhas, aceitar_consolidados)

    outras_linhas = [
        linha
        for linha in linhas
        if linha["chave"].startswith("(-)") and not _eh_agregado_abcd(linha["chave"])
    ]
    outras_deducoes = _somar_linhas(outras_linhas)

    total_aplicado = {
        estagio: quantizar_moeda(
            valores_positivos[estagio]
            - redutor_a[estagio]
            - redutor_b[estagio]
            - redutor_c[estagio]
            - redutor_d[estagio]
            - outras_deducoes[estagio]
        )
        for estagio in ESTAGIOS_DESPESA
    }

    if any(valor < ZERO for valor in total_aplicado.values()):
        raise ErroRegraNegocio(
            "O total aplicado da Parte 2 ficou negativo em pelo menos um estágio; "
            "revise sinais e linhas classificadas."
        )

    if validar_total_final:
        finais = [
            linha
            for linha in linhas
            if "VALOR TOTAL DESTINADO A APLICACAO EM EDUCACAO" in linha["chave"]
        ]
        if len(finais) > 1:
            raise ErroSchemaFlexvision("Há mais de uma linha de total final na Parte 2.")
        if finais:
            for estagio in ESTAGIOS_DESPESA:
                _comparar_decimal(
                    finais[0]["valores"][estagio],
                    total_aplicado[estagio],
                    f"total final da Parte 2 em {estagio}",
                )

    linhas_publicadas = list(linhas_recebidas)
    if total_transferido_fundeb is None and total_fundeb_calculado is not None:
        linhas_publicadas.append(total_fundeb_calculado)
    linhas_publicas = tuple(
        {"descricao": linha["descricao"], **linha["valores"]}
        for linha in linhas_publicadas
    )
    total_fundeb = total_transferido_fundeb or total_fundeb_calculado
    if total_transferido_fundeb is not None and total_fundeb_calculado is not None:
        origem_total_fundeb = "linha direta reconciliada com FUNDEB-FILTRO"
    elif total_transferido_fundeb is not None:
        origem_total_fundeb = "linha direta TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
    else:
        origem_total_fundeb = "0 - linha FUNDEB-FILTRO"
    return ResultadoParte2(
        valores_positivos=valores_positivos,
        redutor_a=redutor_a,
        redutor_b=redutor_b,
        redutor_c=redutor_c,
        redutor_d=redutor_d,
        outras_deducoes=outras_deducoes,
        total_aplicado=total_aplicado,
        detalhes_a=tuple(detalhes_a),
        detalhes_c=tuple(detalhes_c),
        linhas_normalizadas=linhas_publicas,
        total_fundeb=total_fundeb,
        origem_total_fundeb=origem_total_fundeb,
        detalhes_b=detalhes_b,
        detalhes_d=tuple(detalhes_d),
        linhas_positivas=tuple(positivas),
        outras_linhas=tuple(outras_linhas),
    )


def calcular_indice_educacao(
    dados_parte1: Any,
    dados_parte2: Any,
    *,
    estagio_indice: str = "despesa_liquidada",
    colunas_parte1: Mapping[str, str] | None = None,
    colunas_parte2: Mapping[str, str] | None = None,
    aceitar_consolidados_parte2: bool = False,
) -> ResultadoEducacao:
    """Executa as duas partes e entrega métricas prontas para o dashboard."""

    return ResultadoEducacao(
        parte1=calcular_parte1(dados_parte1, colunas=colunas_parte1),
        parte2=calcular_parte2(
            dados_parte2,
            colunas=colunas_parte2,
            aceitar_consolidados=aceitar_consolidados_parte2,
        ),
        estagio_indice=estagio_indice,
    )


def _calcular_redutor_a(
    linhas: Sequence[dict[str, Any]],
    aceitar_consolidados: bool,
) -> tuple[dict[str, Decimal], list[dict[str, Any]]]:
    superavits: dict[str, list[dict[str, Any]]] = {grupo: [] for grupo in GRUPOS_SUPERAVIT}
    aplicacoes: dict[str, list[dict[str, Any]]] = {grupo: [] for grupo in GRUPOS_SUPERAVIT}

    for linha in linhas:
        chave = linha["chave"]
        if "FUNDEB" not in chave or "SUPERAVIT" not in chave:
            continue
        grupo = _grupo_superavit(chave)
        if grupo is None:
            continue
        if "SUPERAVIT FINANCEIRO" in chave:
            superavits[grupo].append(linha)
        elif "APLICACAO DO SUPERAVIT" in chave:
            aplicacoes[grupo].append(linha)

    if not any(superavits.values()) and not any(aplicacoes.values()):
        agregado = _linha_unica(
            linhas,
            lambda chave: "SUPERAVIT PERMITIDO NO EXERCICIO IMEDIATAMENTE ANTERIOR" in chave,
            "redutor A consolidado",
            obrigatoria=False,
        )
        if agregado and aceitar_consolidados:
            _validar_linhas_nao_negativas((agregado,), "redutor A consolidado")
            return dict(agregado["valores"]), []
        raise ErroSchemaFlexvision(
            "Não foram encontrados os quatro insumos brutos do redutor A: "
            "superávit financeiro e aplicação, separados entre impostos e "
            "complementação da União. A linha A consolidada não substitui esses "
            "insumos na execução normal."
        )

    detalhes: list[dict[str, Any]] = []
    total = _serie_zero()
    for grupo in GRUPOS_SUPERAVIT:
        if len(superavits[grupo]) != 1 or len(aplicacoes[grupo]) != 1:
            raise ErroSchemaFlexvision(
                f"O redutor A exige exatamente um superávit e uma aplicação para "
                f"o grupo {grupo!r}; encontrados {len(superavits[grupo])} e "
                f"{len(aplicacoes[grupo])}."
            )
        _validar_linhas_nao_negativas(
            (superavits[grupo][0], aplicacoes[grupo][0]),
            f"insumos do redutor A ({grupo})",
        )
        calculado: dict[str, Decimal] = {}
        for estagio in ESTAGIOS_DESPESA:
            valor = max(
                superavits[grupo][0]["valores"][estagio]
                - aplicacoes[grupo][0]["valores"][estagio],
                ZERO,
            )
            calculado[estagio] = quantizar_moeda(valor)
            total[estagio] += calculado[estagio]
        detalhes.append(
            {
                "grupo": grupo,
                **calculado,
                "superavit": dict(superavits[grupo][0]["valores"]),
                "aplicacao": dict(aplicacoes[grupo][0]["valores"]),
                "redutor": dict(calculado),
            }
        )
    return {estagio: quantizar_moeda(total[estagio]) for estagio in ESTAGIOS_DESPESA}, detalhes


def _calcular_redutor_b(
    linhas: Sequence[dict[str, Any]], aceitar_consolidados: bool
) -> tuple[dict[str, Decimal], dict[str, dict[str, Decimal]]]:
    receita = _linha_unica(
        linhas,
        lambda chave: "RECEITAS RECEBIDAS DO FUNDEB" in chave
        and "NAO UTILIZADAS" not in chave,
        "receitas recebidas do FUNDEB (redutor B)",
        obrigatoria=False,
    )
    despesa = _linha_unica(
        linhas,
        lambda chave: "TOTAL DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB" in chave,
        "despesas custeadas com FUNDEB (redutor B)",
        obrigatoria=False,
    )
    if receita is None and despesa is None:
        agregado = _linha_unica(
            linhas,
            lambda chave: "RECEITAS DO FUNDEB NAO UTILIZADAS NO EXERCICIO" in chave,
            "redutor B consolidado",
            obrigatoria=False,
        )
        if agregado and aceitar_consolidados:
            _validar_linhas_nao_negativas((agregado,), "redutor B consolidado")
            return dict(agregado["valores"]), {}
    if receita is None or despesa is None:
        raise ErroSchemaFlexvision(
            "O redutor B exige as linhas RECEITAS RECEBIDAS DO FUNDEB e TOTAL "
            "DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB."
        )
    _validar_linhas_nao_negativas((receita, despesa), "insumos do redutor B")

    valor_nao_aplicado = {
        estagio: quantizar_moeda(
            receita["valores"][estagio] - despesa["valores"][estagio]
        )
        for estagio in ESTAGIOS_DESPESA
    }
    limite_dez_por_cento = {
        estagio: quantizar_moeda(
            receita["valores"][estagio] * Decimal("0.10")
        )
        for estagio in ESTAGIOS_DESPESA
    }
    redutor = {
        estagio: quantizar_moeda(
            max(
                receita["valores"][estagio]
                - despesa["valores"][estagio]
                - receita["valores"][estagio] * Decimal("0.10"),
                ZERO,
            )
        )
        for estagio in ESTAGIOS_DESPESA
    }
    detalhes = {
        "receita_fundeb": dict(receita["valores"]),
        "despesa_fundeb": dict(despesa["valores"]),
        "valor_nao_aplicado": valor_nao_aplicado,
        "limite_dez_por_cento": limite_dez_por_cento,
        "redutor": dict(redutor),
    }
    return redutor, detalhes


def _calcular_redutor_c(
    linhas: Sequence[dict[str, Any]],
    aceitar_consolidados: bool,
) -> tuple[dict[str, Decimal], list[dict[str, Any]]]:
    restos: dict[int, dict[str, Any]] = {}
    excessos: dict[int, dict[str, Any]] = {}

    for linha in linhas:
        chave = linha["chave"]
        if "TAC" in chave:
            continue
        if "RESTOS A PAGAR CANCELADOS" in chave and ("RPP" in chave or "RPNP" in chave):
            _registrar_linha_por_ano(restos, linha, "restos a pagar cancelados")
        elif "EXCESSO APLICADO EM EDUCACAO" in chave:
            _registrar_linha_por_ano(excessos, linha, "excesso aplicado em educação")

    if not restos and not excessos:
        agregado = _linha_unica(
            linhas,
            lambda chave: "(I) TOTAL DOS RESTOS A PAGAR CANCELADOS - MDE" in chave,
            "redutor C consolidado",
            obrigatoria=False,
        )
        if agregado and aceitar_consolidados:
            _validar_linhas_nao_negativas((agregado,), "redutor C consolidado")
            return dict(agregado["valores"]), []
        raise ErroSchemaFlexvision(
            "Não foram encontrados os insumos brutos do redutor C por exercício. "
            "A linha C consolidada não substitui esses insumos na execução normal."
        )

    total = _serie_zero()
    detalhes: list[dict[str, Any]] = []
    for ano in sorted(set(restos) | set(excessos)):
        _validar_linhas_nao_negativas(
            tuple(linha for linha in (restos.get(ano), excessos.get(ano)) if linha),
            f"insumos do redutor C no exercício {ano}",
        )
        valores_rp = (
            dict(restos[ano]["valores"])
            if ano in restos
            else _serie_zero()
        )
        valores_excesso = (
            dict(excessos[ano]["valores"])
            if ano in excessos
            else _serie_zero()
        )
        calculado: dict[str, Decimal] = {}
        for estagio in ESTAGIOS_DESPESA:
            valor_rp = valores_rp[estagio]
            valor_excesso = valores_excesso[estagio]
            calculado[estagio] = quantizar_moeda(max(valor_rp - valor_excesso, ZERO))
            total[estagio] += calculado[estagio]
        detalhes.append(
            {
                "exercicio_inscricao": ano,
                **calculado,
                "ano": ano,
                "rp_cancelado": valores_rp,
                "excesso_aplicado": valores_excesso,
                "redutor": dict(calculado),
            }
        )
    return {estagio: quantizar_moeda(total[estagio]) for estagio in ESTAGIOS_DESPESA}, detalhes


def _calcular_redutor_d(
    linhas: Sequence[dict[str, Any]], aceitar_consolidados: bool
) -> tuple[dict[str, Decimal], list[dict[str, Any]]]:
    linhas_tac = [
        linha
        for linha in linhas
        if "RP CANCELADO TAC" in linha["chave"] and _extrair_ano(linha["chave"]) is not None
    ]
    if linhas_tac:
        total = _somar_linhas(linhas_tac)
        detalhes = [
            {
                "ano": _extrair_ano(linha["chave"]),
                "valores": dict(linha["valores"]),
            }
            for linha in linhas_tac
        ]
        return total, detalhes

    agregado = _linha_unica(
        linhas,
        lambda chave: "(II) RESTOS A PAGAR CANCELADOS" in chave and "TAC" in chave,
        "redutor D consolidado",
        obrigatoria=False,
    )
    if agregado and aceitar_consolidados:
        _validar_linhas_nao_negativas((agregado,), "redutor D consolidado")
        return dict(agregado["valores"]), []
    raise ErroSchemaFlexvision(
        "Não foram encontrados os insumos brutos do redutor D (RP cancelado TAC "
        "por exercício). A linha D consolidada não substitui esses insumos na "
        "execução normal."
    )


def _eh_agregado_abcd(chave: str) -> bool:
    return any(
        trecho in chave
        for trecho in (
            "SUPERAVIT PERMITIDO NO EXERCICIO IMEDIATAMENTE ANTERIOR",
            "RECEITAS DO FUNDEB NAO UTILIZADAS NO EXERCICIO",
            "RESTOS A PAGAR CANCELADOS (I) - (II)",
            "(I) TOTAL DOS RESTOS A PAGAR CANCELADOS - MDE",
            "(II) RESTOS A PAGAR CANCELADOS",
        )
    )


def _resolver_coluna_descricao(
    registros: Sequence[Mapping[str, Any]],
    override: str | None,
    *,
    termos_linha: Sequence[str],
    nome_parte: str,
) -> str:
    disponiveis = colunas_disponiveis(registros)
    if override:
        if override not in disponiveis:
            raise ErroSchemaFlexvision(
                f"Coluna de descrição {override!r} não existe em {nome_parte}."
            )
        return override

    candidatos: list[str] = []
    for coluna in disponiveis:
        valores = [normalizar_texto(registro.get(coluna)) for registro in registros]
        tem_termo = any(any(termo in valor for termo in termos_linha) for valor in valores)
        tem_linha_assinada = any(
            valor.startswith("(+)") or valor.startswith("(-)") for valor in valores
        )
        if tem_termo or tem_linha_assinada:
            candidatos.append(coluna)
    if len(candidatos) == 1:
        return candidatos[0]
    raise ErroSchemaFlexvision(
        f"Não foi possível identificar unicamente a coluna de descrição da {nome_parte}. "
        f"Colunas recebidas: {', '.join(disponiveis)}."
    )


def _mapear_linha_cabecalho_parte1(
    registros: Sequence[Mapping[str, Any]], coluna_descricao: str
) -> dict[str, str]:
    aliases = {
        nome: tuple(normalizar_texto(alias) for alias in nomes)
        for nome, nomes in ALIASES_PARTE1.items()
    }
    for registro in registros:
        encontrados: dict[str, str] = {}
        for coluna, valor in registro.items():
            if coluna == coluna_descricao:
                continue
            chave = normalizar_texto(valor)
            for nome_logico, nomes in aliases.items():
                if chave in nomes:
                    encontrados[nome_logico] = coluna
        if "prevista" in encontrados and "arrecadada" in encontrados:
            return encontrados
    return {}


def _resolver_coluna(
    disponiveis: Sequence[str],
    nome_logico: str,
    aliases: Sequence[str],
    override: str | None,
    *,
    aceitar_contem: bool,
) -> str:
    if override:
        if override not in disponiveis:
            raise ErroSchemaFlexvision(
                f"A coluna configurada para {nome_logico!r}, {override!r}, não existe."
            )
        return override

    aliases_norm = tuple(normalizar_texto(alias) for alias in aliases)
    candidatos = []
    for coluna in disponiveis:
        chave = normalizar_texto(coluna)
        corresponde = chave in aliases_norm
        if aceitar_contem:
            corresponde = corresponde or any(alias in chave for alias in aliases_norm)
        if corresponde:
            candidatos.append(coluna)
    if len(candidatos) == 1:
        return candidatos[0]
    if len(candidatos) > 1:
        raise ErroSchemaFlexvision(
            f"Mais de uma coluna corresponde a {nome_logico!r}: {', '.join(candidatos)}."
        )
    raise ErroSchemaFlexvision(
        f"Coluna obrigatória {nome_logico!r} ausente. Recebidas: {', '.join(disponiveis)}."
    )


def _resolver_coluna_opcional(
    disponiveis: Sequence[str],
    aliases: Sequence[str],
    override: str | None,
    *,
    aceitar_contem: bool,
) -> str | None:
    if override:
        return _resolver_coluna(
            disponiveis,
            override,
            aliases,
            override,
            aceitar_contem=aceitar_contem,
        )
    aliases_norm = tuple(normalizar_texto(alias) for alias in aliases)
    candidatos = [
        coluna
        for coluna in disponiveis
        if normalizar_texto(coluna) in aliases_norm
        or (aceitar_contem and any(alias in normalizar_texto(coluna) for alias in aliases_norm))
    ]
    if len(candidatos) > 1:
        raise ErroSchemaFlexvision(
            f"Mais de uma coluna opcional corresponde aos aliases: {', '.join(candidatos)}."
        )
    return candidatos[0] if candidatos else None


def _ler_decimal(
    registro: Mapping[str, Any], coluna: str, indice: int, descricao: str
) -> Decimal:
    if coluna not in registro:
        raise ErroSchemaFlexvision(
            f"A linha {indice}, descrição {descricao!r}, não possui a coluna "
            f"obrigatória {coluna!r}."
        )
    try:
        return numero_decimal(registro[coluna])
    except ValueError as erro:
        raise ErroSchemaFlexvision(
            f"Valor inválido na linha {indice}, coluna {coluna!r}, descrição "
            f"{descricao!r}: {registro.get(coluna)!r}."
        ) from erro


def _linha_unica(
    linhas: Sequence[dict[str, Any]],
    predicado: Any,
    nome: str,
    *,
    obrigatoria: bool,
) -> dict[str, Any] | None:
    encontradas = [linha for linha in linhas if predicado(linha["chave"])]
    if len(encontradas) > 1:
        descricoes = "; ".join(linha["descricao"] for linha in encontradas)
        raise ErroSchemaFlexvision(f"Mais de uma linha encontrada para {nome}: {descricoes}.")
    if not encontradas and obrigatoria:
        raise ErroSchemaFlexvision(f"Linha obrigatória ausente: {nome}.")
    return encontradas[0] if encontradas else None


def _grupo_superavit(chave: str) -> str | None:
    if "COMPLEMENTACAO DA UNIAO" in chave:
        return "complementacao_uniao"
    if "IMPOSTOS" in chave:
        return "impostos"
    return None


def _serie_zero() -> dict[str, Decimal]:
    return {estagio: ZERO for estagio in ESTAGIOS_DESPESA}


def _calcular_total_fundeb_do_filtro(
    insumo: dict[str, Any],
) -> dict[str, Any]:
    """Reproduz em Python a expressão Flexvision ``0 - nó-FILTRO``."""

    positivos_no_insumo = [
        estagio
        for estagio, valor in insumo["valores"].items()
        if valor > ZERO
    ]
    if positivos_no_insumo:
        raise ErroRegraNegocio(
            "A expressão do total transferido ao FUNDEB é 0 - valor do nó "
            "FUNDEB-FILTRO, portanto o insumo deve chegar negativo ou zerado. "
            f"Foram encontrados valores positivos em: {', '.join(positivos_no_insumo)}."
        )

    return {
        "indice": insumo["indice"],
        "descricao": "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
        "chave": "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
        "valores": {
            estagio: quantizar_moeda(ZERO - insumo["valores"][estagio])
            for estagio in ESTAGIOS_DESPESA
        },
    }


def _somar_linhas(linhas: Sequence[dict[str, Any]]) -> dict[str, Decimal]:
    _validar_linhas_nao_negativas(linhas, "linhas somadas da Parte 2")
    return {
        estagio: quantizar_moeda(
            sum((linha["valores"][estagio] for linha in linhas), ZERO)
        )
        for estagio in ESTAGIOS_DESPESA
    }


def _validar_linhas_nao_negativas(
    linhas: Sequence[dict[str, Any]], contexto: str
) -> None:
    for linha in linhas:
        negativos = [
            estagio
            for estagio, valor in linha["valores"].items()
            if valor < ZERO
        ]
        if negativos:
            raise ErroRegraNegocio(
                f"A linha {linha['descricao']!r} contém valores negativos em "
                f"{', '.join(negativos)} ({contexto}). Na Parte 2, as deduções "
                "devem chegar como magnitudes positivas; o código aplica a subtração."
            )


def _registrar_linha_por_ano(
    destino: dict[int, dict[str, Any]], linha: dict[str, Any], nome: str
) -> None:
    ano = _extrair_ano(linha["chave"])
    if ano is None:
        raise ErroSchemaFlexvision(
            f"Não foi possível identificar o exercício na linha de {nome}: "
            f"{linha['descricao']!r}."
        )
    if ano in destino:
        raise ErroSchemaFlexvision(
            f"Há mais de uma linha de {nome} para o exercício {ano}."
        )
    destino[ano] = linha


def _extrair_ano(chave: str) -> int | None:
    anos = re.findall(r"\b(?:19|20)\d{2}\b", chave)
    return int(anos[-1]) if anos else None


def _validar_valor_informado(
    registro: Mapping[str, Any], coluna: str, esperado: Decimal, nome: str
) -> None:
    recebido = quantizar_moeda(numero_decimal(registro.get(coluna)))
    _comparar_decimal(recebido, esperado, nome)


def _validar_percentual_informado(
    registro: Mapping[str, Any], coluna: str, esperado: Decimal, nome: str
) -> None:
    recebido = numero_decimal(registro.get(coluna))
    if abs(recebido - esperado) > Decimal("0.01"):
        raise ErroRegraNegocio(
            f"Divergência no {nome}: informado={recebido}, recalculado={esperado}."
        )


def _comparar_decimal(recebido: Decimal, esperado: Decimal, nome: str) -> None:
    if abs(recebido - esperado) > CENTAVO:
        raise ErroRegraNegocio(
            f"Divergência no {nome}: informado={recebido}, recalculado={esperado}."
        )
