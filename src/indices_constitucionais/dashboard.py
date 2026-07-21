"""Preparação de dados para a interface Streamlit, sem regras financeiras novas."""

from __future__ import annotations

import os
import hashlib
import hmac
import secrets
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .educacao import calcular_indice_educacao
from .flexvision import (
    CONSULTA_PARTE1,
    CONSULTA_PARTE2,
    consultar_e_calcular_educacao,
)
from .fontes import ler_csv_parte1, ler_csv_parte2
from .modelos import (
    ESTAGIOS_DESPESA,
    ROTULOS_ESTAGIOS,
    ResultadoEducacao,
    validar_estagio,
)
from .normalizacao import ZERO, formatar_brl, formatar_percentual, normalizar_texto


RAIZ_PROJETO = Path(__file__).resolve().parents[2]
PASTA_CONSULTAS_PADRAO = RAIZ_PROJETO / "consultas_base"
_SAL_ESCOPO_CREDENCIAL = secrets.token_bytes(32)


def carregar_resultado_referencia(
    pasta_consultas: str | Path = PASTA_CONSULTAS_PADRAO,
) -> ResultadoEducacao:
    """Carrega a Parte 1 e a Parte 2 adaptada com insumos brutos A–D."""

    pasta = Path(pasta_consultas)
    arquivo_parte1 = _arquivo_unico(pasta, "*Parte 1_3 (2026)_*.csv", "Parte 1")
    arquivo_parte2 = _arquivo_unico(
        pasta,
        "*Parte 2_3 (2026) com FR 108 Adaptado_*.csv",
        "Parte 2 adaptada",
    )
    return calcular_indice_educacao(
        ler_csv_parte1(arquivo_parte1),
        ler_csv_parte2(arquivo_parte2),
    )


def carregar_resultado_api(
    exercicio: int,
    periodo: int,
    *,
    consulta_parte1: str = CONSULTA_PARTE1,
    consulta_parte2: str = CONSULTA_PARTE2,
    timeout: int = 300,
) -> ResultadoEducacao:
    """Consulta o Flexvision sem expor ou persistir credenciais no resultado."""

    from siaferio import SiafeAPI

    usuario, senha = _ler_credenciais_api()

    with SiafeAPI(usuario=usuario, senha=senha) as api:
        return consultar_e_calcular_educacao(
            api,
            exercicio=int(exercicio),
            periodo=int(periodo),
            consulta_parte1=consulta_parte1,
            consulta_parte2=consulta_parte2,
            timeout=timeout,
        )


def escopo_credenciais_api() -> str:
    """Identifica uma rotação de credenciais sem guardar usuário ou senha."""

    usuario, senha = _ler_credenciais_api()
    mensagem = f"{usuario}\0{senha}".encode("utf-8")
    return hmac.new(_SAL_ESCOPO_CREDENCIAL, mensagem, hashlib.sha256).hexdigest()[:24]


def montar_view_model(
    resultado: ResultadoEducacao,
    estagio: str = "despesa_liquidada",
) -> dict[str, Any]:
    """Converte o resultado em textos e séries estáveis para a página."""

    validar_estagio(estagio)
    metricas = resultado.metricas_dashboard(estagio)
    indice = metricas["indice_aplicacao_percentual"]
    margem = metricas["margem_pontos_percentuais"]
    atingimento = metricas["atingimento_do_minimo_percentual"]

    if indice is None:
        situacao = {
            "tipo": "warning",
            "titulo": "Índice indisponível",
            "mensagem": "A base arrecadada é zero; não é possível calcular o percentual.",
        }
    elif metricas["atingiu_minimo"]:
        situacao = {
            "tipo": "success",
            "titulo": "Percentual do estágio ≥ 25%",
            "mensagem": (
                f"No estágio {ROTULOS_ESTAGIOS[estagio].lower()}, o percentual "
                "calculado é igual ou superior a 25%."
            ),
        }
    else:
        situacao = {
            "tipo": "error",
            "titulo": "Percentual do estágio < 25%",
            "mensagem": (
                f"No estágio {ROTULOS_ESTAGIOS[estagio].lower()}, o percentual "
                "calculado está abaixo de 25%."
            ),
        }

    if indice is None:
        saldo_rotulo = "Saldo do mínimo do período"
        saldo_valor = None
        saldo_tipo = "indisponivel"
    elif metricas["deficit_para_minimo"] > ZERO:
        saldo_rotulo = "Falta para o mínimo do período"
        saldo_valor = metricas["deficit_para_minimo"]
        saldo_tipo = "deficit"
    elif metricas["excedente_sobre_minimo"] > ZERO:
        saldo_rotulo = "Excedente sobre o mínimo do período"
        saldo_valor = metricas["excedente_sobre_minimo"]
        saldo_tipo = "excedente"
    else:
        saldo_rotulo = "No mínimo do período — 25%"
        saldo_valor = ZERO
        saldo_tipo = "limite"

    cards = (
        {
            "rotulo": "Índice do período — base arrecadada",
            "valor": formatar_percentual_decisorio(indice),
            "delta": _formatar_pontos_percentuais(margem),
            "ajuda": "Aplicação do estágio selecionado dividida pela receita arrecadada.",
        },
        {
            "rotulo": f"Aplicação — {ROTULOS_ESTAGIOS[estagio]}",
            "valor": formatar_brl_compacto(metricas["aplicacao_educacao"]),
            "delta": None,
            "ajuda": (
                "Valor total após a aplicação de todos os redutores. "
                f"Valor exato: {formatar_brl(metricas['aplicacao_educacao'])}."
            ),
        },
        {
            "rotulo": "Mínimo do período — 25% da arrecadada",
            "valor": formatar_brl_compacto(metricas["minimo_constitucional"]),
            "delta": None,
            "ajuda": (
                "25% da receita arrecadada considerada na Parte 1. "
                f"Valor exato: {formatar_brl(metricas['minimo_constitucional'])}."
            ),
        },
        {
            "rotulo": saldo_rotulo,
            "valor": formatar_brl_compacto(saldo_valor),
            "delta": None,
            "ajuda": (
                "Diferença monetária entre a aplicação e o mínimo do período. "
                f"Valor exato: {formatar_brl(saldo_valor)}."
            ),
            "tipo": saldo_tipo,
        },
    )

    return {
        "estagio": estagio,
        "rotulo_estagio": ROTULOS_ESTAGIOS[estagio],
        "metricas": metricas,
        "cards": cards,
        "situacao": situacao,
        "atingimento_percentual": atingimento,
        "linhas_estagios": montar_linhas_estagios(resultado),
        "linhas_redutores": montar_linhas_redutores(resultado, estagio),
        "quadro_resumo": montar_quadro_resumo_formatado(resultado),
        "relatorio_calculado": montar_relatorio_calculado_formatado(resultado),
        "componentes_receita": montar_componentes_receita(resultado),
        "detalhes_a": montar_detalhes_formatados(resultado.parte2.detalhes_a),
        "detalhes_c": montar_detalhes_formatados(resultado.parte2.detalhes_c),
        "visao_anual": montar_visao_anual(resultado),
        "avisos": resultado.parte1.avisos,
    }


def montar_visao_anual(resultado: ResultadoEducacao) -> dict[str, Any]:
    """Monta a visão gerencial anual sempre pela despesa liquidada."""

    metricas = resultado.metricas_dashboard("despesa_liquidada")
    deficit = metricas["deficit_para_minimo_previsto"]
    excedente = metricas["excedente_sobre_minimo_previsto"]
    if metricas["indice_sobre_receita_prevista_percentual"] is None:
        saldo_rotulo = "Saldo da meta anual indisponível"
        saldo_valor = None
    elif deficit > ZERO:
        saldo_rotulo = "Falta para a meta anual prevista"
        saldo_valor = deficit
    elif excedente > ZERO:
        saldo_rotulo = "Excedente sobre a meta anual prevista"
        saldo_valor = excedente
    else:
        saldo_rotulo = "Saldo da meta anual prevista"
        saldo_valor = ZERO

    cards = (
        {
            "rotulo": "Receita prevista no exercício",
            "valor": formatar_brl_compacto(metricas["receita_prevista"]),
            "ajuda": f"Valor exato: {formatar_brl(metricas['receita_prevista'])}.",
        },
        {
            "rotulo": "Meta anual prevista — 25%",
            "valor": formatar_brl_compacto(
                metricas["minimo_constitucional_previsto"]
            ),
            "ajuda": (
                "25% da receita prevista para o exercício. "
                f"Valor exato: {formatar_brl(metricas['minimo_constitucional_previsto'])}."
            ),
        },
        {
            "rotulo": "Despesa liquidada acumulada",
            "valor": formatar_brl_compacto(metricas["aplicacao_educacao"]),
            "ajuda": (
                "Aplicação liquidada após os redutores. "
                f"Valor exato: {formatar_brl(metricas['aplicacao_educacao'])}."
            ),
        },
        {
            "rotulo": "Execução da meta anual",
            "valor": formatar_percentual_decisorio(
                metricas["atingimento_do_minimo_previsto_percentual"],
                Decimal("100"),
            ),
            "ajuda": "Despesa liquidada dividida pela meta anual prevista de 25%.",
        },
        {
            "rotulo": saldo_rotulo,
            "valor": formatar_brl_compacto(saldo_valor),
            "ajuda": f"Valor exato: {formatar_brl(saldo_valor)}.",
        },
    )
    return {
        "estagio": "despesa_liquidada",
        "rotulo_estagio": ROTULOS_ESTAGIOS["despesa_liquidada"],
        "metricas": metricas,
        "cards": cards,
        "indice_previsto_formatado": formatar_percentual_decisorio(
            metricas["indice_sobre_receita_prevista_percentual"]
        ),
        "atingimento_meta_formatado": formatar_percentual_decisorio(
            metricas["atingimento_do_minimo_previsto_percentual"], Decimal("100")
        ),
    }


def montar_linhas_estagios(resultado: ResultadoEducacao) -> tuple[dict[str, Any], ...]:
    """Série comparativa dos cinco estágios, mantendo ``Decimal``."""

    linhas = []
    for estagio in ESTAGIOS_DESPESA:
        metricas = resultado.metricas_dashboard(estagio)
        linhas.append(
            {
                "estagio": estagio,
                "rotulo": ROTULOS_ESTAGIOS[estagio],
                "aplicacao": metricas["aplicacao_educacao"],
                "indice_percentual": metricas["indice_aplicacao_percentual"],
                "indice_formatado": formatar_percentual_decisorio(
                    metricas["indice_aplicacao_percentual"]
                ),
                "margem_pp": metricas["margem_pontos_percentuais"],
                "atingiu_minimo": metricas["atingiu_minimo"],
            }
        )
    return tuple(linhas)


def montar_linhas_redutores(
    resultado: ResultadoEducacao, estagio: str
) -> tuple[dict[str, Any], ...]:
    """Abre os redutores do estágio selecionado."""

    validar_estagio(estagio)
    parte2 = resultado.parte2
    series = (
        ("A — superávit anterior", parte2.redutor_a),
        ("B — FUNDEB acima de 10%", parte2.redutor_b),
        ("C — RP cancelados MDE", parte2.redutor_c),
        ("D — RP cancelados TAC", parte2.redutor_d),
        ("Outras deduções", parte2.outras_deducoes),
    )
    return tuple(
        {
            "redutor": rotulo,
            "valor": valores[estagio],
            "valor_formatado": formatar_brl(valores[estagio]),
        }
        for rotulo, valores in series
    )


def montar_quadro_resumo_formatado(
    resultado: ResultadoEducacao,
) -> tuple[dict[str, str], ...]:
    """Formata o quadro completo para evitar ``Decimal`` como objeto no Arrow."""

    return tuple(
        {
            "Métrica": linha["metrica"],
            **{
                ROTULOS_ESTAGIOS[estagio]: formatar_brl(linha[estagio])
                for estagio in ESTAGIOS_DESPESA
            },
        }
        for linha in resultado.parte2.quadro_resumo()
    )


def montar_relatorio_calculado_formatado(
    resultado: ResultadoEducacao,
) -> tuple[dict[str, str], ...]:
    """Formata a Parte 2 pós-cálculo no leiaute lógico do relatório antigo."""

    return tuple(
        {
            "Valores aplicados em educação — Função 12": str(linha["descricao"]),
            **{
                ROTULOS_ESTAGIOS[estagio]: formatar_brl(linha[estagio])
                for estagio in ESTAGIOS_DESPESA
            },
        }
        for linha in resultado.parte2.relatorio_calculado()
    )


def montar_componentes_receita(
    resultado: ResultadoEducacao,
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "Componente": str(linha["descricao"]),
            "Receita prevista": formatar_brl(linha["receita_prevista"]),
            "Receita arrecadada": formatar_brl(linha["receita_arrecadada"]),
        }
        for linha in resultado.parte1.componentes
    )


def montar_detalhes_formatados(
    detalhes: tuple[dict[str, Any], ...],
) -> tuple[dict[str, str], ...]:
    linhas: list[dict[str, str]] = []
    for detalhe in detalhes:
        identificador = detalhe.get("grupo", detalhe.get("exercicio_inscricao", "—"))
        linhas.append(
            {
                "Grupo/exercício": str(identificador).replace("_", " ").title(),
                **{
                    ROTULOS_ESTAGIOS[estagio]: formatar_brl(detalhe[estagio])
                    for estagio in ESTAGIOS_DESPESA
                },
            }
        )
    return tuple(linhas)


def mensagem_erro_segura(erro: Exception) -> str:
    """Resume falhas da API sem incluir URL, credenciais ou payload integral."""

    resposta = getattr(erro, "response", None)
    if resposta is not None:
        status = getattr(resposta, "status_code", "desconhecido")
        consulta_id = getattr(erro, "consulta_id", None)
        tentativas = getattr(erro, "tentativas", 1)
        orientacoes = {
            401: "Confira as credenciais e a etapa adicional de autenticação.",
            403: "A conta autenticada não possui acesso à consulta.",
            404: (
                f"Confira os identificadores {CONSULTA_PARTE1} e "
                f"{CONSULTA_PARTE2}."
            ),
            429: "O limite de requisições foi atingido; tente novamente depois.",
            500: "O servidor encontrou uma falha interna ao processar uma das consultas.",
        }
        orientacao = orientacoes.get(
            status,
            "Tente novamente ou verifique a disponibilidade da API.",
        )
        prefixo = f"Consulta {consulta_id}: " if consulta_id else ""
        complemento = (
            f" após {tentativas} tentativas" if tentativas and tentativas > 1 else ""
        )
        return (
            f"{prefixo}Flexvision respondeu HTTP {status}{complemento}. "
            f"{orientacao}{_detalhe_formula_flexvision(resposta)}"
        )

    nome = erro.__class__.__name__
    if nome in {"ErroSchemaFlexvision", "ErroRegraNegocio", "FileNotFoundError"}:
        return str(erro) or nome
    if isinstance(erro, RuntimeError) and str(erro).startswith("Credenciais ausentes"):
        return str(erro)
    if "Timeout" in nome:
        return "A consulta excedeu o tempo máximo de resposta."
    if "Connection" in nome or "Request" in nome:
        return "Não foi possível comunicar com a API do SIAFE-Rio."
    return f"Falha de carga ({nome}). Tente novamente ou acione o suporte técnico."


def _detalhe_formula_flexvision(resposta: Any) -> str:
    """Traduz apenas fórmulas conhecidas, sem publicar o corpo arbitrário da API."""

    try:
        payload = resposta.json()
    except (AttributeError, TypeError, ValueError):
        return ""
    if not isinstance(payload, dict) or not isinstance(payload.get("erro"), str):
        return ""

    detalhe = normalizar_texto(payload["erro"])
    if "RESTOS A PAGAR CANCELADOS (I) - (II)" in detalhe:
        return (
            " A falha ocorreu ao avaliar a expressão consolidada de Restos a "
            "Pagar Cancelados (I) - (II); remova essa expressão da consulta API."
        )
    if (
        "RECEITAS DO FUNDEB NAO UTILIZADAS NO EXERCICIO" in detalhe
        or "VALOR NAO APLICADO" in detalhe
    ):
        return (
            " A falha ocorreu ao avaliar a expressão consolidada do redutor B; "
            "remova o SE dessa linha e mantenha seus dois insumos brutos."
        )
    if "SUPERAVIT PERMITIDO NO EXERCICIO IMEDIATAMENTE ANTERIOR" in detalhe:
        return (
            " A falha ocorreu ao avaliar a expressão consolidada do redutor A; "
            "mantenha somente os quatro insumos brutos do superávit."
        )
    return ""


def _arquivo_unico(pasta: Path, padrao: str, nome: str) -> Path:
    encontrados = sorted(pasta.glob(padrao))
    if len(encontrados) != 1:
        raise FileNotFoundError(
            f"Esperado exatamente um CSV da {nome} em {pasta}; "
            f"encontrados {len(encontrados)}."
        )
    return encontrados[0]


def _ler_credenciais_api() -> tuple[str, str]:
    from dotenv import dotenv_values

    arquivo_env = dotenv_values(RAIZ_PROJETO / ".env")
    usuario = os.getenv("SIAFE_USUARIO") or arquivo_env.get("SIAFE_USUARIO")
    senha = os.getenv("SIAFE_SENHA") or arquivo_env.get("SIAFE_SENHA")
    if not usuario or not senha:
        raise RuntimeError(
            "Credenciais ausentes. Defina SIAFE_USUARIO e SIAFE_SENHA no arquivo .env."
        )
    return str(usuario), str(senha)


def _formatar_pontos_percentuais(valor: Any) -> str | None:
    if valor is None:
        return None
    casas = _casas_que_preservam_relacao(valor, ZERO)
    if casas is None:
        direcao = "abaixo" if valor < ZERO else "acima"
        return f"{direcao} de 25% por menos de 0,000000000001 p.p."
    passo = Decimal(1).scaleb(-casas)
    valor_formatado = valor.quantize(passo, rounding=ROUND_HALF_UP)
    sinal = "+" if valor > ZERO else ""
    numero = f"{valor_formatado:.{casas}f}".replace(".", ",")
    return f"{sinal}{numero} p.p. ante 25%"


def formatar_percentual_decisorio(
    valor: Decimal | None,
    limite: Decimal = Decimal("25"),
) -> str:
    """Evita que o arredondamento visual esconda o lado real do limite."""

    if valor is None:
        return "—"
    casas = _casas_que_preservam_relacao(valor, limite)
    if casas is None:
        operador = "<" if valor < limite else ">"
        return f"{operador} {formatar_percentual(limite)}"
    return formatar_percentual(valor, casas=casas)


def formatar_brl_compacto(valor: Decimal | None) -> str:
    """Formata cards sem truncar bilhões e preserva o valor exato na ajuda."""

    if valor is None:
        return "—"
    absoluto = abs(valor)
    if absoluto >= Decimal("1000000000"):
        divisor, sufixo = Decimal("1000000000"), "bi"
    elif absoluto >= Decimal("1000000"):
        divisor, sufixo = Decimal("1000000"), "mi"
    else:
        return formatar_brl(valor)
    reduzido = (valor / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    numero = f"{reduzido:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {numero} {sufixo}"


def _casas_que_preservam_relacao(valor: Decimal, limite: Decimal) -> int | None:
    if valor == limite:
        return 2
    for casas in (2, 4, 6, 8, 10, 12):
        passo = Decimal(1).scaleb(-casas)
        arredondado = valor.quantize(passo, rounding=ROUND_HALF_UP)
        if valor < limite and arredondado < limite:
            return casas
        if valor > limite and arredondado > limite:
            return casas
    return None
