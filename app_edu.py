"""Dashboard didático do índice constitucional da educação.

Este arquivo foi escrito para ser lido de cima para baixo e executado sozinho:

1. define as consultas e os estágios da despesa;
2. busca os dois JSONs no Flexvision;
3. recompõe a base constitucional de receitas (Parte 1);
4. calcula a aplicação em educação e os redutores A, B, C e D (Parte 2);
5. transforma os resultados em métricas;
6. apresenta o dashboard e a memória de cálculo no Streamlit.

Não existe leitura de CSV nem troca automática de fonte. Em produção, todos os
valores exibidos por este app vêm das consultas 084835 e 084837.

GUIA DE LEITURA
---------------

* As seções 1 a 3 preparam a configuração e buscam os JSONs.
* A seção 4 produz o dicionário ``parte1`` com as bases de receita.
* A seção 5 produz o dicionário ``parte2`` com positivos, A–D, outras
  deduções e o total aplicado em cada estágio.
* A seção 6 combina ``parte1`` e ``parte2`` e produz as métricas decisórias.
* As seções 7 e 8 somente formatam e exibem o resultado; elas não criam uma
  nova regra financeira.

CONVENÇÕES IMPORTANTES
----------------------

* dinheiro permanece como ``Decimal`` durante todo o cálculo;
* uma série financeira é um dicionário com o mesmo valor lógico nos cinco
  estágios: dotação, autorizada, empenhada, liquidada e paga;
* na Parte 1, linhas ``(-)`` já chegam negativas e são somadas com esse sinal;
* na Parte 2, deduções chegam como magnitudes positivas e o Python as subtrai;
* a API só é chamada dentro do clique do botão no final do arquivo.

VOCABULÁRIO USADO NO CÓDIGO
---------------------------

``payload`` é o JSON recebido; ``registro`` é um objeto desse JSON; ``linha``
é o registro já convertido para a estrutura interna; e ``valores`` é o mapa
dos cinco estágios financeiros. Se um ID ou uma regra mudar, atualize também
``VERSAO_CALCULO`` e os testes de reconciliação.
"""

from __future__ import annotations

import math
import os
import re
import time
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

import altair as alt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ``pandas``, ``Altair`` e ``Plotly`` aparecem apenas na apresentação. Eles não
# participam das contas financeiras, que continuam integralmente em Decimal.


# =============================================================================
# 1. CONFIGURAÇÃO
# =============================================================================

# Parte 1: receitas prevista e arrecadada.
CONSULTA_RECEITAS = "084835"

# Parte 2: despesas e insumos brutos usados nos cálculos A, B, C e D.
CONSULTA_DESPESAS = "084837"

# Alterar esta versão invalida um resultado antigo guardado na sessão.
VERSAO_CALCULO = "app-edu-v1-084835-084837"

META_CONSTITUCIONAL = Decimal("25")
ALIQUOTA_MINIMA = Decimal("0.25")
ZERO = Decimal("0")
CENTAVO = Decimal("0.01")

# META_CONSTITUCIONAL está na escala percentual (25); ALIQUOTA_MINIMA está na
# escala de multiplicação (0,25). Manter as duas evita conversões implícitas.

# Os cinco estágios são calculados e ficam disponíveis para auditoria. A ordem
# deste dicionário também determina a ordem das colunas nas tabelas:
#
# - dotação atual: orçamento atualizado disponível;
# - despesa autorizada: limite autorizado para executar a despesa;
# - empenhada: obrigação assumida pela Administração;
# - liquidada: bem/serviço entregue e direito do credor reconhecido;
# - paga: saída financeira efetivada.
ESTAGIOS = {
    "dotacao_atual": "Dotação atual",
    "despesa_autorizada": "Despesa autorizada",
    "despesa_empenhada": "Despesa empenhada",
    "despesa_liquidada": "Despesa liquidada",
    "despesa_paga": "Despesa paga",
}

# No gráfico comparativo mostramos apenas os três estágios de execução pedidos.
# A liquidada é o padrão do índice por representar a despesa já reconhecida; a
# seleção continua analítica e não substitui a interpretação jurídica.
ESTAGIOS_COMPARACAO = (
    "despesa_empenhada",
    "despesa_liquidada",
    "despesa_paga",
)

ALIASES_ESTAGIOS = {
    "dotacao_atual": ("DOTACAO ATUAL",),
    "despesa_autorizada": ("DESPESA AUTORIZADA",),
    "despesa_empenhada": ("DESPESA EMPENHADA",),
    "despesa_liquidada": ("DESPESA LIQUIDADA",),
    "despesa_paga": ("DESPESA PAGA",),
}

# Os aliases desacoplam o nome interno usado no Python do cabeçalho apresentado
# pelo Flexvision. Se um cabeçalho mudar, a falha ocorre antes de qualquer soma.

STATUS_HTTP_QUE_PODEM_SER_REPETIDOS = {500, 502, 503, 504}


class ErroDadosEducacao(Exception):
    """Erro de estrutura ou de regra de negócio que pode ser explicado na tela."""


class ErroConsultaFlexvision(ErroDadosEducacao):
    """Falha segura de uma consulta, sem guardar resposta, senha ou token."""

    def __init__(self, consulta_id: str, status_http: int | None, tentativas: int):
        self.consulta_id = consulta_id
        self.status_http = status_http
        self.tentativas = tentativas
        status = f"HTTP {status_http}" if status_http is not None else "erro de comunicação"
        super().__init__(
            f"A consulta {consulta_id} falhou com {status} após {tentativas} tentativa(s)."
        )


# =============================================================================
# 2. FUNÇÕES PEQUENAS DE NORMALIZAÇÃO E FORMATAÇÃO
# =============================================================================

def normalizar_texto(valor: Any) -> str:
    """Retira acentos e diferenças de caixa para comparar títulos de linhas."""

    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(
        caractere for caractere in texto if not unicodedata.combining(caractere)
    )
    texto = texto.upper().replace("\xa0", " ")
    return " ".join(texto.split())


def para_decimal(valor: Any, *, vazio_como_zero: bool = True) -> Decimal:
    """Converte números da API para Decimal, inclusive no padrão brasileiro.

    Exemplos aceitos: ``5.194.807.180,76``, ``5194807180.76``, ``R$ 1.234,56``
    e valores negativos. Decimal é usado para não perder centavos.
    """

    if isinstance(valor, Decimal):
        return valor
    if valor is None:
        if vazio_como_zero:
            return ZERO
        raise ValueError("Valor numérico ausente.")
    if isinstance(valor, bool):
        raise ValueError("Valor booleano não é um número financeiro válido.")
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        if not math.isfinite(valor):
            if vazio_como_zero:
                return ZERO
            raise ValueError("Valor numérico não finito.")
        return Decimal(str(valor))

    texto_original = str(valor).strip().replace("\xa0", " ")
    if normalizar_texto(texto_original) in {"", "NAN", "NONE", "NULL", "N/A", "-"}:
        if vazio_como_zero:
            return ZERO
        raise ValueError("Valor numérico ausente.")

    negativo_parenteses = texto_original.startswith("(") and texto_original.endswith(")")
    texto = texto_original.replace("R$", "").replace("%", "").replace(" ", "")
    texto = re.sub(r"[^0-9,.+\-]", "", texto)
    negativo_final = texto.endswith("-")
    texto = texto.rstrip("-")

    if "," in texto and "." in texto:
        # O último separador é tratado como decimal.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        partes = texto.split(",")
        if len(partes) == 2:
            texto = ".".join(partes)
        elif len(partes[-1]) <= 2:
            texto = "".join(partes[:-1]) + "." + partes[-1]
        else:
            texto = "".join(partes)
    elif texto.count(".") > 1:
        partes = texto.split(".")
        if len(partes[-1]) <= 2:
            texto = "".join(partes[:-1]) + "." + partes[-1]
        else:
            texto = "".join(partes)

    try:
        numero = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(f"Valor numérico inválido: {valor!r}.") from erro

    if negativo_parenteses or negativo_final:
        numero = -abs(numero)
    return numero


def moeda(valor: Decimal) -> Decimal:
    """Arredonda um valor financeiro para centavos."""

    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def minimo_25_por_cento(base: Decimal) -> Decimal:
    """Calcula 25% e eleva eventual fração de centavo para o próximo centavo.

    ``ROUND_CEILING`` é deliberado: o mínimo monetário nunca pode representar
    menos que 25% por causa de uma fração de centavo. Os demais valores usam o
    arredondamento financeiro comum, ``ROUND_HALF_UP``.
    """

    return (base * ALIQUOTA_MINIMA).quantize(CENTAVO, rounding=ROUND_CEILING)


def formatar_brl(valor: Decimal | None) -> str:
    """Formata o valor exato em reais; nenhuma conta é feita com esse texto."""

    if valor is None:
        return "—"
    numero = f"{moeda(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {numero}"


def formatar_brl_compacto(valor: Decimal | None) -> str:
    """Reduz milhões/bilhões somente para caber nos cards do dashboard."""

    if valor is None:
        return "—"
    absoluto = abs(valor)
    if absoluto >= Decimal("1000000000"):
        divisor, sufixo = Decimal("1000000000"), "bi"
    elif absoluto >= Decimal("1000000"):
        divisor, sufixo = Decimal("1000000"), "mi"
    else:
        return formatar_brl(valor)
    reduzido = (valor / divisor).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    numero = f"{reduzido:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {numero} {sufixo}"


def formatar_percentual(valor: Decimal | None, casas: int = 2) -> str:
    """Formata um percentual que já está na escala 0–100."""

    if valor is None:
        return "—"
    passo = Decimal(1).scaleb(-casas)
    numero = f"{valor.quantize(passo, rounding=ROUND_HALF_UP):.{casas}f}"
    return numero.replace(".", ",") + "%"


def percentual(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    """Calcula numerador ÷ denominador × 100; zero na base gera indisponível."""

    return numerador * Decimal("100") / denominador if denominador else None


def serie_zero() -> dict[str, Decimal]:
    """Cria uma série zerada para acumular valores nos cinco estágios."""

    return {estagio: ZERO for estagio in ESTAGIOS}


def extrair_registros(payload: Any) -> list[dict[str, Any]]:
    """Extrai a lista de linhas de um JSON sem escolher uma coleção ambígua.

    Entrada: retorno literal do client Flexvision, que pode ser uma lista ou um
    envelope como ``{"dados": [...]}``. Saída: sempre uma lista de dicionários.
    Se houver duas listas possíveis, o app interrompe em vez de adivinhar.
    """

    if payload is None:
        return []

    if hasattr(payload, "to_dict") and not isinstance(payload, Mapping):
        try:
            payload = payload.to_dict(orient="records")
        except TypeError:
            pass

    if isinstance(payload, Mapping):
        preferidas = [
            payload[chave]
            for chave in ("dados", "data", "items", "records", "resultado", "resultados")
            if chave in payload and isinstance(payload[chave], list)
        ]
        if len(preferidas) == 1:
            payload = preferidas[0]
        else:
            listas = [valor for valor in payload.values() if isinstance(valor, list)]
            if len(listas) == 1:
                payload = listas[0]
            elif len(listas) > 1:
                raise ErroDadosEducacao(
                    "O JSON contém mais de uma lista; não é seguro adivinhar qual é a consulta."
                )
            else:
                payload = [payload]

    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        raise ErroDadosEducacao(
            f"Formato de resposta não suportado: {type(payload).__name__}."
        )

    registros: list[dict[str, Any]] = []
    for indice, item in enumerate(payload):
        if not isinstance(item, Mapping):
            raise ErroDadosEducacao(f"O item {indice} da resposta não é um objeto JSON.")
        registros.append({str(chave): valor for chave, valor in item.items()})
    return registros


def colunas_disponiveis(registros: Sequence[Mapping[str, Any]]) -> list[str]:
    """Lista uma vez cada chave presente nas linhas, preservando a ordem."""

    colunas: list[str] = []
    for registro in registros:
        for coluna in registro:
            if coluna not in colunas:
                colunas.append(coluna)
    return colunas


def encontrar_coluna_descricao(
    registros: Sequence[Mapping[str, Any]], termos: Sequence[str]
) -> str:
    """Encontra a coluna textual que contém as descrições das linhas.

    Ela é reconhecida pelo conteúdo, como ``(+) Fonte 100`` ou
    ``TOTAL - BASE DE CÁLCULO``, e não por um título fixo que poderia mudar.
    """

    candidatos: list[str] = []
    for coluna in colunas_disponiveis(registros):
        valores = [normalizar_texto(registro.get(coluna)) for registro in registros]
        tem_assinatura = any(
            valor.startswith("(+)") or valor.startswith("(-)") for valor in valores
        )
        tem_termo = any(any(termo in valor for termo in termos) for valor in valores)
        if tem_assinatura or tem_termo:
            candidatos.append(coluna)
    if len(candidatos) != 1:
        raise ErroDadosEducacao(
            "Não foi possível identificar uma única coluna de descrição. "
            f"Candidatas: {', '.join(candidatos) or 'nenhuma'}."
        )
    return candidatos[0]


def encontrar_coluna(
    registros: Sequence[Mapping[str, Any]],
    aliases: Sequence[str],
    nome: str,
    *,
    aceitar_contem: bool,
    obrigatoria: bool = True,
) -> str | None:
    """Resolve um cabeçalho da API pelos aliases e exige resultado único.

    ``aceitar_contem`` é usado na Parte 1 porque os títulos atuais incluem
    marcadores como ``(A)`` e ``(B)``. Na Parte 2 exigimos o título exato.
    """

    aliases_normalizados = tuple(normalizar_texto(alias) for alias in aliases)
    candidatos = []
    for coluna in colunas_disponiveis(registros):
        chave = normalizar_texto(coluna)
        corresponde = chave in aliases_normalizados
        if aceitar_contem:
            corresponde = corresponde or any(alias in chave for alias in aliases_normalizados)
        if corresponde:
            candidatos.append(coluna)

    if len(candidatos) > 1:
        raise ErroDadosEducacao(
            f"Mais de uma coluna corresponde a {nome}: {', '.join(candidatos)}."
        )
    if not candidatos and obrigatoria:
        recebidas = ", ".join(colunas_disponiveis(registros))
        raise ErroDadosEducacao(
            f"Coluna obrigatória {nome!r} ausente. Colunas recebidas: {recebidas}."
        )
    return candidatos[0] if candidatos else None


def ler_valor(
    registro: Mapping[str, Any], coluna: str, indice: int, descricao: str
) -> Decimal:
    """Lê uma célula obrigatória e acrescenta contexto a um eventual erro.

    Uma célula presente, porém vazia, é tratada como zero pela normalização.
    Uma coluna ausente é quebra do contrato da API e interrompe o cálculo.
    """

    if coluna not in registro:
        raise ErroDadosEducacao(
            f"A linha {indice}, {descricao!r}, não possui a coluna {coluna!r}."
        )
    try:
        return para_decimal(registro[coluna])
    except ValueError as erro:
        raise ErroDadosEducacao(
            f"Valor financeiro inválido na linha {indice}, coluna {coluna!r}."
        ) from erro


def linha_unica(
    linhas: Sequence[dict[str, Any]],
    condicao: Callable[[str], bool],
    nome: str,
    *,
    obrigatoria: bool = True,
) -> dict[str, Any] | None:
    """Localiza uma linha de negócio e impede duplicidade silenciosa.

    Isso é importante porque somar duas linhas que representam o mesmo insumo
    produziria um resultado plausível, porém contabilizado em dobro.
    """

    encontradas = [linha for linha in linhas if condicao(linha["chave"])]
    if len(encontradas) > 1:
        descricoes = "; ".join(linha["descricao"] for linha in encontradas)
        raise ErroDadosEducacao(f"Mais de uma linha encontrada para {nome}: {descricoes}.")
    if not encontradas and obrigatoria:
        raise ErroDadosEducacao(f"Linha obrigatória ausente: {nome}.")
    return encontradas[0] if encontradas else None


def validar_nao_negativas(linhas: Sequence[dict[str, Any]], contexto: str) -> None:
    """Na Parte 2 os redutores chegam positivos; o Python faz a subtração."""

    for linha in linhas:
        negativos = [
            ESTAGIOS[estagio]
            for estagio, valor in linha["valores"].items()
            if valor < ZERO
        ]
        if negativos:
            raise ErroDadosEducacao(
                f"A linha {linha['descricao']!r} tem valor negativo em "
                f"{', '.join(negativos)} ({contexto})."
            )


def somar_linhas(linhas: Sequence[dict[str, Any]]) -> dict[str, Decimal]:
    """Soma uma coleção de linhas separadamente em cada estágio."""

    validar_nao_negativas(linhas, "soma da Parte 2")
    return {
        estagio: moeda(sum((linha["valores"][estagio] for linha in linhas), ZERO))
        for estagio in ESTAGIOS
    }


def comparar_centavos(recebido: Decimal, calculado: Decimal, nome: str) -> None:
    """Usa uma linha pronta apenas como controle, com tolerância de um centavo.

    A tolerância absorve diferenças de arredondamento da exportação. Acima de
    R$ 0,01, a divergência deixa de ser silenciosa e interrompe o resultado.
    """

    if abs(recebido - calculado) > CENTAVO:
        raise ErroDadosEducacao(
            f"Divergência em {nome}: recebido={recebido}, calculado={calculado}."
        )


# =============================================================================
# 3. EXTRAÇÃO — AS DUAS CONSULTAS USAM A MESMA SESSÃO DA API
# =============================================================================

def ler_credenciais() -> tuple[str, str]:
    """Lê usuário e senha do ambiente ou do .env, sem mostrá-los na página."""

    from dotenv import dotenv_values

    arquivo_env = dotenv_values(Path(__file__).resolve().with_name(".env"))
    usuario = os.getenv("SIAFE_USUARIO") or arquivo_env.get("SIAFE_USUARIO")
    senha = os.getenv("SIAFE_SENHA") or arquivo_env.get("SIAFE_SENHA")
    if not usuario or not senha:
        raise ErroDadosEducacao(
            "Credenciais ausentes. Defina SIAFE_USUARIO e SIAFE_SENHA no arquivo .env."
        )
    return str(usuario), str(senha)


def consultar_com_retentativa(
    api: Any,
    consulta_id: str,
    parametros: list[int],
    *,
    timeout: int = 300,
    tentativas: int = 3,
) -> Any:
    """Repete somente falhas HTTP transitórias: 500, 502, 503 e 504.

    Erros como 401, 403 e 404 não tendem a desaparecer com uma nova tentativa;
    repeti-los apenas atrasaria um diagnóstico de credencial ou configuração.
    """

    for tentativa in range(1, tentativas + 1):
        try:
            return api.flexvision.consultar(
                consulta_id,
                parametros=parametros,
                timeout=timeout,
            )
        except Exception as erro:
            resposta = getattr(erro, "response", None)
            status = getattr(resposta, "status_code", None)
            pode_repetir = (
                status in STATUS_HTTP_QUE_PODEM_SER_REPETIDOS and tentativa < tentativas
            )
            if pode_repetir:
                time.sleep(2 ** (tentativa - 1))  # 1 segundo e depois 2 segundos
                continue
            raise ErroConsultaFlexvision(consulta_id, status, tentativa) from erro

    raise AssertionError("Fluxo de consulta terminou sem retorno ou erro.")


def buscar_dados_api(exercicio: int, periodo: int) -> tuple[Any, Any]:
    """Busca Parte 1 e Parte 2. Não há fallback para CSV.

    Ano e período são enviados, nessa ordem, às duas consultas e dentro da
    mesma sessão autenticada. Assim, receita e despesa pertencem à mesma
    referência e não há mistura silenciosa de fontes.
    """

    try:
        from siaferio import SiafeAPI
    except ImportError as erro:
        raise ErroDadosEducacao(
            "O client siaferio não está instalado neste ambiente Python."
        ) from erro

    usuario, senha = ler_credenciais()
    parametros = [int(exercicio), int(periodo)]
    with SiafeAPI(usuario=usuario, senha=senha) as api:
        parte1 = consultar_com_retentativa(api, CONSULTA_RECEITAS, parametros)
        parte2 = consultar_com_retentativa(api, CONSULTA_DESPESAS, parametros)
    return parte1, parte2


# =============================================================================
# 4. PARTE 1 — BASE CONSTITUCIONAL DE RECEITAS E MÍNIMO DE 25%
# =============================================================================

def calcular_parte1(payload: Any) -> dict[str, Any]:
    """Soma os componentes de receita e calcula os mínimos do período e anual.

    Entrada: JSON da 084835. Saída: componentes, bases prevista/arrecadada,
    realização da receita e mínimos de 25%. Receita prevista e arrecadada são
    indispensáveis; diferença e percentual são opcionais porque são refeitos.
    """

    registros = extrair_registros(payload)
    if not registros:
        raise ErroDadosEducacao("A consulta 084835 não retornou registros.")

    # Contrato da API: primeiro identificamos o esquema. Nenhum valor é somado
    # antes de confirmar quais colunas representam descrição, prevista e
    # arrecadada.
    coluna_descricao = encontrar_coluna_descricao(
        registros, termos=("TOTAL - BASE DE CALCULO",)
    )
    coluna_prevista = encontrar_coluna(
        registros,
        ("RECEITA PREVISTA",),
        "Receita Prevista",
        aceitar_contem=True,
    )
    coluna_arrecadada = encontrar_coluna(
        registros,
        ("RECEITA ARRECADADA",),
        "Receita Arrecadada",
        aceitar_contem=True,
    )
    coluna_diferenca = encontrar_coluna(
        registros,
        ("DIFERENCA (B-A)", "DIFERENCA B-A", "DIFERENCA"),
        "Diferença (B-A)",
        aceitar_contem=True,
        obrigatoria=False,
    )
    coluna_percentual = encontrar_coluna(
        registros,
        ("ARRECADADA/PREVISTA", "ARRECADADA PREVISTA", "B/A"),
        "Arrecadada/Prevista",
        aceitar_contem=True,
        obrigatoria=False,
    )
    assert coluna_prevista is not None and coluna_arrecadada is not None

    componentes: list[dict[str, Any]] = []
    total_informado: Mapping[str, Any] | None = None
    minimo_informado: Mapping[str, Any] | None = None

    # Regra financeira: somente linhas assinadas com (+) ou (-) formam a base.
    # TOTAL, mínimo e separadores são guardados/ignorados para que nunca sejam
    # somados como se fossem um componente adicional.
    for indice, registro in enumerate(registros):
        if coluna_descricao not in registro:
            raise ErroDadosEducacao(
                f"A linha {indice} da Parte 1 não possui a coluna de descrição."
            )
        descricao = str(registro.get(coluna_descricao) or "").strip()
        chave = normalizar_texto(descricao)
        if not chave or chave == "SEPARADOR":
            continue
        if chave.startswith("TOTAL - BASE DE CALCULO"):
            total_informado = registro
            continue
        if "VALOR A SER APLICADO EM EDUCACAO" in chave:
            minimo_informado = registro
            continue
        if not (chave.startswith("(+)") or chave.startswith("(-)")):
            continue

        prevista = ler_valor(registro, coluna_prevista, indice, descricao)
        arrecadada = ler_valor(registro, coluna_arrecadada, indice, descricao)

        # Na Parte 1, a transferência aos municípios já vem com sinal negativo.
        if chave.startswith("(-)") and (prevista > ZERO or arrecadada > ZERO):
            raise ErroDadosEducacao(
                f"A linha redutora {descricao!r} da Parte 1 deve chegar negativa."
            )
        componentes.append(
            {
                "descricao": descricao,
                "receita_prevista": prevista,
                "receita_arrecadada": arrecadada,
            }
        )

    if not componentes:
        raise ErroDadosEducacao("Nenhum componente (+) ou (-) foi encontrado na Parte 1.")

    # Recompomos as duas bases a partir dos componentes, preservando o sinal de
    # cada linha. O total pronto da API será usado apenas para reconciliar.
    base_prevista = moeda(sum((item["receita_prevista"] for item in componentes), ZERO))
    base_arrecadada = moeda(
        sum((item["receita_arrecadada"] for item in componentes), ZERO)
    )
    if base_prevista < ZERO or base_arrecadada < ZERO:
        raise ErroDadosEducacao("A base constitucional não pode ser negativa.")

    # Fórmulas da Parte 1:
    # realização = arrecadada / prevista; mínimo = base × 25%.
    diferenca = moeda(base_arrecadada - base_prevista)
    realizacao = percentual(base_arrecadada, base_prevista)
    minimo_previsto = minimo_25_por_cento(base_prevista)
    minimo_arrecadado = minimo_25_por_cento(base_arrecadada)
    avisos: list[str] = []

    # Controle de qualidade: as linhas TOTAL servem como oráculos de conferência;
    # elas não alimentam o resultado. Divergência revela mudança ou erro na API.
    if total_informado is not None:
        comparar_centavos(
            ler_valor(total_informado, coluna_prevista, -1, "TOTAL - BASE DE CÁLCULO"),
            base_prevista,
            "base prevista",
        )
        comparar_centavos(
            ler_valor(total_informado, coluna_arrecadada, -1, "TOTAL - BASE DE CÁLCULO"),
            base_arrecadada,
            "base arrecadada",
        )
        if coluna_diferenca:
            comparar_centavos(
                ler_valor(total_informado, coluna_diferenca, -1, "TOTAL - BASE DE CÁLCULO"),
                diferenca,
                "diferença entre receitas",
            )
        if coluna_percentual and realizacao is not None:
            informado = ler_valor(
                total_informado, coluna_percentual, -1, "TOTAL - BASE DE CÁLCULO"
            )
            if abs(informado - realizacao) > Decimal("0.01"):
                raise ErroDadosEducacao("O percentual arrecadada/prevista não reconciliou.")
    else:
        avisos.append("A linha TOTAL da Parte 1 não veio; a base foi recomposta.")

    if minimo_informado is not None:
        comparar_centavos(
            ler_valor(minimo_informado, coluna_prevista, -1, "MÍNIMO DE 25%"),
            minimo_previsto,
            "mínimo sobre a receita prevista",
        )
        comparar_centavos(
            ler_valor(minimo_informado, coluna_arrecadada, -1, "MÍNIMO DE 25%"),
            minimo_arrecadado,
            "mínimo sobre a receita arrecadada",
        )

    return {
        "componentes": componentes,
        "base_prevista": base_prevista,
        "base_arrecadada": base_arrecadada,
        "diferenca": diferenca,
        "realizacao_percentual": realizacao,
        "minimo_previsto": minimo_previsto,
        "minimo_arrecadado": minimo_arrecadado,
        "avisos": avisos,
    }


# =============================================================================
# 5. PARTE 2 — APLICAÇÃO EFETIVA E REDUTORES A, B, C E D
# =============================================================================

def preparar_linhas_parte2(payload: Any) -> list[dict[str, Any]]:
    """Transforma o JSON da 084837 na estrutura interna da Parte 2.

    Cada item de saída contém ``indice``, ``descricao``, uma ``chave`` sem
    acentos para classificação e ``valores`` nos cinco estágios. Mesmo que o
    gráfico mostre só três estágios, todos são calculados para auditoria.
    """

    registros = extrair_registros(payload)
    if not registros:
        raise ErroDadosEducacao("A consulta 084837 não retornou registros.")

    coluna_descricao = encontrar_coluna_descricao(
        registros, termos=("FONTE 100", "RECEITAS RECEBIDAS DO FUNDEB")
    )
    colunas_estagios = {
        estagio: encontrar_coluna(
            registros,
            ALIASES_ESTAGIOS[estagio],
            ESTAGIOS[estagio],
            aceitar_contem=False,
        )
        for estagio in ESTAGIOS
    }

    linhas: list[dict[str, Any]] = []
    for indice, registro in enumerate(registros):
        if coluna_descricao not in registro:
            raise ErroDadosEducacao(
                f"A linha {indice} da Parte 2 não possui a coluna de descrição."
            )
        descricao = str(registro.get(coluna_descricao) or "").strip()
        if not descricao:
            continue
        valores = {
            estagio: ler_valor(
                registro,
                str(coluna),
                indice,
                descricao,
            )
            for estagio, coluna in colunas_estagios.items()
        }
        linhas.append(
            {
                "indice": indice,
                "descricao": descricao,
                "chave": normalizar_texto(descricao),
                "valores": valores,
            }
        )
    return linhas


def resolver_total_transferido_fundeb(
    linhas: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Obtém a linha positiva do FUNDEB, inclusive pelo nó bruto -FILTRO.

    A consulta atual entrega ``...FUNDEB-FILTRO`` com valores negativos. A antiga
    expressão do Flexvision era ``0 - FILTRO``; por isso o mesmo cálculo é feito
    explicitamente aqui. O nó bruto é retirado antes das somas para não duplicar.

    Casos aceitos:

    * linha positiva direta: usa a linha direta;
    * somente FUNDEB-FILTRO: cria uma linha positiva por ``0 - filtro``;
    * ambos: confere que são iguais e usa uma única linha;
    * nenhum: interrompe, pois a aplicação ficaria subestimada.

    A linha direta é um dado positivo comum e preferencial. O filtro é apenas a
    alternativa técnica necessária quando a antiga expressão não chega no JSON.
    """

    linha_direta = linha_unica(
        linhas,
        lambda chave: (
            "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB" in chave
            and "FILTRO" not in chave
        ),
        "total direto das receitas transferidas ao FUNDEB",
        obrigatoria=False,
    )
    linha_filtro = linha_unica(
        linhas,
        lambda chave: "FUNDEB" in chave and "FILTRO" in chave,
        "insumo FUNDEB-FILTRO",
        obrigatoria=False,
    )

    if linha_direta is None and linha_filtro is None:
        raise ErroDadosEducacao(
            "A Parte 2 não trouxe o total positivo do FUNDEB nem o nó FUNDEB-FILTRO."
        )

    sintetica: dict[str, Any] | None = None
    if linha_filtro is not None:
        positivos = [
            ESTAGIOS[estagio]
            for estagio, valor in linha_filtro["valores"].items()
            if valor > ZERO
        ]
        if positivos:
            raise ErroDadosEducacao(
                "O nó FUNDEB-FILTRO deve chegar negativo ou zerado, pois a fórmula é "
                f"0 - FILTRO. Valores positivos em: {', '.join(positivos)}."
            )
        sintetica = {
            "indice": linha_filtro["indice"],
            "descricao": "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
            "chave": "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
            "valores": {
                estagio: moeda(ZERO - linha_filtro["valores"][estagio])
                for estagio in ESTAGIOS
            },
        }

    if linha_direta is not None:
        if not linha_direta["chave"].startswith("(+)"):
            raise ErroDadosEducacao(
                "O total direto do FUNDEB precisa estar identificado com (+)."
            )
        validar_nao_negativas((linha_direta,), "total transferido ao FUNDEB")
        if sintetica is not None:
            for estagio in ESTAGIOS:
                comparar_centavos(
                    linha_direta["valores"][estagio],
                    sintetica["valores"][estagio],
                    f"total do FUNDEB em {ESTAGIOS[estagio]}",
                )
        total_escolhido = linha_direta
        origem = "linha positiva direta da consulta"
    else:
        assert sintetica is not None
        total_escolhido = sintetica
        origem = "0 - valor do nó FUNDEB-FILTRO"

    # Regra contra dupla contagem: o filtro nunca participa diretamente da soma.
    # Se só ele veio, inserimos exatamente uma linha positiva sintética. Assim,
    # o mesmo montante não é somado como filtro e como total reconstruído.
    linhas_calculo = [linha for linha in linhas if linha is not linha_filtro]
    if linha_direta is None:
        linhas_calculo.append(total_escolhido)
    return linhas_calculo, total_escolhido, origem


def grupo_superavit(chave: str) -> str | None:
    """Classifica uma linha do A em um dos dois grupos exigidos pela regra."""

    if "COMPLEMENTACAO DA UNIAO" in chave:
        return "Complementação da União"
    if "IMPOSTOS" in chave:
        return "Impostos e transferências de impostos"
    return None


def calcular_redutor_a(
    linhas: Sequence[dict[str, Any]],
) -> tuple[dict[str, Decimal], list[dict[str, Any]]]:
    """A = soma, por grupo, de max(superávit - aplicação, 0).

    São esperadas quatro linhas: superávit e aplicação para impostos; superávit
    e aplicação para complementação da União. ``max(..., 0)`` significa que uma
    aplicação maior que o superávit zera o redutor, nunca o torna negativo.
    """

    grupos = {
        "Impostos e transferências de impostos": {"superavit": [], "aplicacao": []},
        "Complementação da União": {"superavit": [], "aplicacao": []},
    }

    for linha in linhas:
        chave = linha["chave"]
        if "FUNDEB" not in chave or "SUPERAVIT" not in chave:
            continue
        grupo = grupo_superavit(chave)
        if grupo is None:
            continue
        if "SUPERAVIT FINANCEIRO" in chave:
            grupos[grupo]["superavit"].append(linha)
        elif "APLICACAO DO SUPERAVIT" in chave:
            grupos[grupo]["aplicacao"].append(linha)

    total = serie_zero()
    detalhes: list[dict[str, Any]] = []
    for grupo, insumos in grupos.items():
        if len(insumos["superavit"]) != 1 or len(insumos["aplicacao"]) != 1:
            raise ErroDadosEducacao(
                "O redutor A exige um superávit financeiro e uma aplicação para "
                f"{grupo}. Encontrados: {len(insumos['superavit'])} e "
                f"{len(insumos['aplicacao'])}."
            )
        superavit = insumos["superavit"][0]
        aplicacao = insumos["aplicacao"][0]
        validar_nao_negativas((superavit, aplicacao), f"redutor A — {grupo}")

        calculado: dict[str, Decimal] = {}
        for estagio in ESTAGIOS:
            calculado[estagio] = moeda(
                max(
                    superavit["valores"][estagio] - aplicacao["valores"][estagio],
                    ZERO,
                )
            )
            total[estagio] += calculado[estagio]

        detalhes.append(
            {
                "grupo": grupo,
                "superavit": dict(superavit["valores"]),
                "aplicacao": dict(aplicacao["valores"]),
                "redutor": calculado,
            }
        )

    return {estagio: moeda(total[estagio]) for estagio in ESTAGIOS}, detalhes


def calcular_redutor_b(
    linhas: Sequence[dict[str, Any]],
) -> tuple[dict[str, Decimal], dict[str, dict[str, Decimal]]]:
    """Calcula o valor do FUNDEB não utilizado acima da tolerância de 10%.

    B1 = receita recebida − despesa custeada; B2 = 10% da receita recebida;
    B = máximo entre (B1 − B2) e zero. B1 pode aparecer negativo na memória,
    mas o redutor final nunca pode ser menor que zero.
    """

    receita = linha_unica(
        linhas,
        lambda chave: (
            "RECEITAS RECEBIDAS DO FUNDEB" in chave and "NAO UTILIZADAS" not in chave
        ),
        "receitas recebidas do FUNDEB",
    )
    despesa = linha_unica(
        linhas,
        lambda chave: "TOTAL DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB" in chave,
        "despesas custeadas com recursos do FUNDEB",
    )
    assert receita is not None and despesa is not None
    validar_nao_negativas((receita, despesa), "redutor B")

    valor_nao_aplicado: dict[str, Decimal] = {}
    limite_dez_por_cento: dict[str, Decimal] = {}
    redutor: dict[str, Decimal] = {}
    for estagio in ESTAGIOS:
        # Os dois intermediários arredondados são guardados para a memória. A
        # fórmula do redutor usa os insumos originais e arredonda só no final.
        valor_nao_aplicado[estagio] = moeda(
            receita["valores"][estagio] - despesa["valores"][estagio]
        )
        limite_dez_por_cento[estagio] = moeda(
            receita["valores"][estagio] * Decimal("0.10")
        )
        redutor[estagio] = moeda(
            max(
                receita["valores"][estagio]
                - despesa["valores"][estagio]
                - receita["valores"][estagio] * Decimal("0.10"),
                ZERO,
            )
        )

    detalhes = {
        "receita_fundeb": dict(receita["valores"]),
        "despesa_fundeb": dict(despesa["valores"]),
        "valor_nao_aplicado": valor_nao_aplicado,
        "limite_dez_por_cento": limite_dez_por_cento,
        "redutor": redutor,
    }
    return redutor, detalhes


def extrair_ano(chave: str) -> int | None:
    """Obtém o último ano de quatro dígitos encontrado no título da linha."""

    anos = re.findall(r"\b(?:19|20)\d{2}\b", chave)
    return int(anos[-1]) if anos else None


def registrar_por_ano(
    destino: dict[int, dict[str, Any]], linha: dict[str, Any], nome: str
) -> None:
    """Registra um único insumo por ano e rejeita duplicidade."""

    ano = extrair_ano(linha["chave"])
    if ano is None:
        raise ErroDadosEducacao(
            f"Não foi possível identificar o ano na linha de {nome}: {linha['descricao']!r}."
        )
    if ano in destino:
        raise ErroDadosEducacao(f"Há mais de uma linha de {nome} para {ano}.")
    destino[ano] = linha


def calcular_redutor_c(
    linhas: Sequence[dict[str, Any]],
) -> tuple[dict[str, Decimal], list[dict[str, Any]]]:
    """C = soma anual de max(RP cancelado - excesso já aplicado, 0).

    RP significa Restos a Pagar. A classificação usa o significado do título,
    não a letra C/D, porque esses prefixos estão invertidos na consulta bruta.
    Linhas do TAC pertencem ao D e são excluídas daqui.
    """

    restos: dict[int, dict[str, Any]] = {}
    excessos: dict[int, dict[str, Any]] = {}
    for linha in linhas:
        chave = linha["chave"]
        if "TAC" in chave:
            continue
        if "RESTOS A PAGAR CANCELADOS" in chave and ("RPP" in chave or "RPNP" in chave):
            registrar_por_ano(restos, linha, "RP cancelado")
        elif "EXCESSO APLICADO EM EDUCACAO" in chave:
            registrar_por_ano(excessos, linha, "excesso aplicado")

    if not restos and not excessos:
        raise ErroDadosEducacao("Os insumos anuais do redutor C não foram encontrados.")

    total = serie_zero()
    detalhes: list[dict[str, Any]] = []
    for ano in sorted(set(restos) | set(excessos)):
        rp = restos.get(ano)
        excesso = excessos.get(ano)
        validar_nao_negativas(
            tuple(item for item in (rp, excesso) if item is not None),
            f"redutor C — {ano}",
        )
        # Se apenas um lado do par anual existir, o lado ausente vale zero. Já
        # duas linhas do mesmo tipo/ano são rejeitadas por registrar_por_ano().
        valores_rp = rp["valores"] if rp else serie_zero()
        valores_excesso = excesso["valores"] if excesso else serie_zero()
        calculado = {
            estagio: moeda(max(valores_rp[estagio] - valores_excesso[estagio], ZERO))
            for estagio in ESTAGIOS
        }
        for estagio in ESTAGIOS:
            total[estagio] += calculado[estagio]
        detalhes.append(
            {
                "ano": ano,
                "rp_cancelado": dict(valores_rp),
                "excesso_aplicado": dict(valores_excesso),
                "redutor": calculado,
            }
        )

    return {estagio: moeda(total[estagio]) for estagio in ESTAGIOS}, detalhes


def calcular_redutor_d(
    linhas: Sequence[dict[str, Any]],
) -> tuple[dict[str, Decimal], list[dict[str, Any]]]:
    """D = somatório das linhas de RP cancelado vinculadas ao TAC.

    TAC significa Termo de Ajustamento de Conduta. A seleção exige o texto
    ``RP CANCELADO TAC`` e um ano, independentemente do prefixo C/D. Exigir o
    ano impede que uma linha visual agregada entre no somatório.
    """

    linhas_tac = [
        linha
        for linha in linhas
        if "RP CANCELADO TAC" in linha["chave"] and extrair_ano(linha["chave"]) is not None
    ]
    if not linhas_tac:
        raise ErroDadosEducacao("Os insumos anuais do redutor D/TAC não foram encontrados.")
    total = somar_linhas(linhas_tac)
    detalhes = [
        {"ano": extrair_ano(linha["chave"]), "valores": dict(linha["valores"])}
        for linha in linhas_tac
    ]
    return total, detalhes


def eh_linha_abcd_consolidada(chave: str) -> bool:
    """Evita subtrair novamente um agregado antigo do Flexvision.

    Como A–D já são recompostos a partir dos insumos brutos, uma linha pronta
    não pode reaparecer como ``outra dedução``.
    """

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


def calcular_parte2(payload: Any) -> dict[str, Any]:
    """Executa todas as regras da Parte 2 para cada estágio da despesa.

    Entrada: JSON bruto da 084837. Saída: valores positivos, redutores A–D,
    outras deduções, total aplicado e memórias que alimentam as tabelas.
    """

    linhas_recebidas = preparar_linhas_parte2(payload)
    linhas, total_fundeb, origem_total_fundeb = resolver_total_transferido_fundeb(
        linhas_recebidas
    )

    # Linhas (+) formam o valor bruto aplicado. O FUNDEB-FILTRO já foi removido
    # ou transformado em uma única linha positiva na etapa anterior.
    linhas_positivas = [linha for linha in linhas if linha["chave"].startswith("(+)")]
    if not linhas_positivas:
        raise ErroDadosEducacao("Nenhuma linha positiva foi encontrada na Parte 2.")
    valores_positivos = somar_linhas(linhas_positivas)

    # A–D são calculados dos insumos brutos, sempre por estágio.
    redutor_a, detalhes_a = calcular_redutor_a(linhas)
    redutor_b, detalhes_b = calcular_redutor_b(linhas)
    redutor_c, detalhes_c = calcular_redutor_c(linhas)
    redutor_d, detalhes_d = calcular_redutor_d(linhas)

    # O prefixo (-) classifica as deduções ordinárias, mas seus números chegam
    # como magnitudes positivas. Agregados A–D são excluídos para não deduzir
    # duas vezes uma regra que acabou de ser recalculada.
    outras_linhas = [
        linha
        for linha in linhas
        if linha["chave"].startswith("(-)")
        and not eh_linha_abcd_consolidada(linha["chave"])
    ]
    outras_deducoes = somar_linhas(outras_linhas)

    # Regra financeira central: C e D são ambos redutores e ambos são
    # subtraídos, apesar de o título legado do relatório mencionar (I) - (II).
    # Aplicação = positivos - A - B - C - D - outras deduções.
    total_aplicado = {
        estagio: moeda(
            valores_positivos[estagio]
            - redutor_a[estagio]
            - redutor_b[estagio]
            - redutor_c[estagio]
            - redutor_d[estagio]
            - outras_deducoes[estagio]
        )
        for estagio in ESTAGIOS
    }
    if any(valor < ZERO for valor in total_aplicado.values()):
        raise ErroDadosEducacao(
            "O total aplicado ficou negativo; revise sinais e classificações da Parte 2."
        )

    # Se o Flexvision trouxer uma linha final, ela funciona somente como conferência.
    total_informado = linha_unica(
        linhas,
        lambda chave: "VALOR TOTAL DESTINADO A APLICACAO EM EDUCACAO" in chave,
        "valor total destinado à educação",
        obrigatoria=False,
    )
    if total_informado is not None:
        for estagio in ESTAGIOS:
            comparar_centavos(
                total_informado["valores"][estagio],
                total_aplicado[estagio],
                f"total aplicado em {ESTAGIOS[estagio]}",
            )

    return {
        "linhas_brutas": linhas_recebidas,
        "linhas_positivas": linhas_positivas,
        "total_fundeb": total_fundeb,
        "origem_total_fundeb": origem_total_fundeb,
        "valores_positivos": valores_positivos,
        "redutor_a": redutor_a,
        "redutor_b": redutor_b,
        "redutor_c": redutor_c,
        "redutor_d": redutor_d,
        "outras_linhas": outras_linhas,
        "outras_deducoes": outras_deducoes,
        "total_aplicado": total_aplicado,
        "detalhes_a": detalhes_a,
        "detalhes_b": detalhes_b,
        "detalhes_c": detalhes_c,
        "detalhes_d": detalhes_d,
    }


# =============================================================================
# 6. MÉTRICAS — NUMERADOR, BASE, ÍNDICE, DÉFICIT E VISÃO ANUAL
# =============================================================================

def calcular_metricas(
    parte1: dict[str, Any], parte2: dict[str, Any], estagio: str
) -> dict[str, Any]:
    """Cria as métricas do estágio escolhido e a visão anual gerencial.

    Existem quatro leituras diferentes, todas úteis:

    * índice do período = estágio selecionado / receita arrecadada;
    * cobertura do mínimo = estágio selecionado / (25% da arrecadada);
    * índice anual = despesa liquidada / receita prevista;
    * execução da meta anual = liquidada / (25% da prevista).

    Por isso, por exemplo, 8,76% sobre toda a previsão pode representar 35,02%
    de execução do montante-alvo. São denominadores diferentes, não resultados
    concorrentes.
    """

    if estagio not in ESTAGIOS:
        raise ErroDadosEducacao(f"Estágio inválido: {estagio}.")

    # Visão oficial do período: muda o numerador conforme o estágio escolhido,
    # mas mantém a receita arrecadada como denominador.
    aplicado = parte2["total_aplicado"][estagio]
    base_arrecadada = parte1["base_arrecadada"]
    minimo_periodo = parte1["minimo_arrecadado"]
    indice_periodo = percentual(aplicado, base_arrecadada)
    margem_pp = indice_periodo - META_CONSTITUCIONAL if indice_periodo is not None else None
    saldo_periodo = moeda(aplicado - minimo_periodo)

    # Visão anual gerencial: usa sempre a despesa liquidada e a receita prevista,
    # independentemente do seletor do período.
    liquidado = parte2["total_aplicado"]["despesa_liquidada"]
    base_prevista = parte1["base_prevista"]
    minimo_anual = parte1["minimo_previsto"]
    indice_anual = percentual(liquidado, base_prevista)
    execucao_meta_anual = percentual(liquidado, minimo_anual)
    saldo_anual = moeda(liquidado - minimo_anual)

    return {
        "estagio": estagio,
        "aplicado": aplicado,
        "base_arrecadada": base_arrecadada,
        "minimo_periodo": minimo_periodo,
        "indice_periodo": indice_periodo,
        "margem_pp": margem_pp,
        "saldo_periodo": saldo_periodo,
        "deficit_periodo": max(-saldo_periodo, ZERO),
        "excedente_periodo": max(saldo_periodo, ZERO),
        "cobertura_minimo": percentual(aplicado, minimo_periodo),
        # A decisão usa o Decimal completo. O texto arredondado do card nunca
        # decide sozinho se o percentual atingiu 25%.
        "atingiu_minimo": indice_periodo is not None
        and indice_periodo >= META_CONSTITUCIONAL,
        "liquidado": liquidado,
        "base_prevista": base_prevista,
        "minimo_anual": minimo_anual,
        "indice_anual": indice_anual,
        "execucao_meta_anual": execucao_meta_anual,
        "saldo_anual": saldo_anual,
        "deficit_anual": max(-saldo_anual, ZERO),
        "excedente_anual": max(saldo_anual, ZERO),
    }


def calcular_todos_os_indices(
    parte1: dict[str, Any], parte2: dict[str, Any]
) -> list[dict[str, Any]]:
    """Calcula as três barras usando a mesma base arrecadada."""

    linhas = []
    for estagio in ESTAGIOS_COMPARACAO:
        metricas = calcular_metricas(parte1, parte2, estagio)
        linhas.append(
            {
                "estagio": estagio,
                "rotulo": ESTAGIOS[estagio],
                "indice": metricas["indice_periodo"],
                "aplicado": metricas["aplicado"],
                "atingiu": metricas["atingiu_minimo"],
            }
        )
    return linhas


# =============================================================================
# 7. TABELAS E GRÁFICOS — SOMENTE APRESENTAÇÃO, SEM NOVAS REGRAS FINANCEIRAS
# =============================================================================

def linha_financeira(rotulo: str, valores: Mapping[str, Decimal]) -> dict[str, str]:
    """Converte uma série Decimal em uma linha já formatada para a tabela."""

    return {
        "Componente": rotulo,
        **{ESTAGIOS[estagio]: formatar_brl(valores[estagio]) for estagio in ESTAGIOS},
    }


def quadro_formacao_aplicacao(parte2: dict[str, Any]) -> list[dict[str, str]]:
    """Memória da fórmula positivos - A - B - C - D - outras deduções."""

    return [
        linha_financeira("(+) Valores positivos", parte2["valores_positivos"]),
        linha_financeira("(-) A — superávit anterior", parte2["redutor_a"]),
        linha_financeira("(-) B — FUNDEB não aplicado acima de 10%", parte2["redutor_b"]),
        linha_financeira("(-) C — RP cancelados MDE", parte2["redutor_c"]),
        linha_financeira("(-) D — RP cancelados TAC", parte2["redutor_d"]),
        linha_financeira("(-) Outras deduções", parte2["outras_deducoes"]),
        linha_financeira("(=) Total aplicado em educação", parte2["total_aplicado"]),
    ]


def relatorio_calculado(parte2: dict[str, Any]) -> list[dict[str, str]]:
    """Recria o desenho lógico do relatório após calcular A–D em Python.

    A linha C+D preserva a aparência do relatório antigo. As linhas individuais
    C e D logo abaixo são memória informativa; não são somadas novamente.
    """

    linhas: list[dict[str, str]] = []
    for linha in parte2["linhas_positivas"]:
        linhas.append(linha_financeira(linha["descricao"], linha["valores"]))
    linhas.append(
        linha_financeira(
            "(-) A — superávit permitido anterior não aplicado", parte2["redutor_a"]
        )
    )
    linhas.append(
        linha_financeira(
            "(-) B — receitas do FUNDEB não utilizadas acima de 10%",
            parte2["redutor_b"],
        )
    )
    for linha in parte2["outras_linhas"]:
        linhas.append(linha_financeira(linha["descricao"], linha["valores"]))
    redutor_c_d = {
        estagio: moeda(parte2["redutor_c"][estagio] + parte2["redutor_d"][estagio])
        for estagio in ESTAGIOS
    }
    linhas.extend(
        [
            linha_financeira("(-) Restos a Pagar Cancelados (C + D)", redutor_c_d),
            linha_financeira("(I) Total dos Restos a Pagar Cancelados — MDE", parte2["redutor_c"]),
            linha_financeira("(II) Restos a Pagar Cancelados — TAC", parte2["redutor_d"]),
            linha_financeira("VALOR TOTAL DESTINADO À EDUCAÇÃO", parte2["total_aplicado"]),
        ]
    )
    return linhas


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


def formula_monetaria(parte2: dict[str, Any], estagio: str) -> str:
    """Fórmula da aplicação já preenchida com valores do estágio selecionado."""

    return (
        f"{formatar_brl(parte2['valores_positivos'][estagio])}"
        f" - {formatar_brl(parte2['redutor_a'][estagio])}"
        f" - {formatar_brl(parte2['redutor_b'][estagio])}"
        f" - {formatar_brl(parte2['redutor_c'][estagio])}"
        f" - {formatar_brl(parte2['redutor_d'][estagio])}"
        f" - {formatar_brl(parte2['outras_deducoes'][estagio])}"
        f" = {formatar_brl(parte2['total_aplicado'][estagio])}"
    )


def diagnostico_seguro(erro: Exception) -> str:
    """Produz uma mensagem útil sem exibir senha, token ou payload integral."""

    if isinstance(erro, ErroConsultaFlexvision):
        return str(erro)
    if isinstance(erro, ErroDadosEducacao):
        return str(erro)
    if erro.__class__.__name__ == "SiafeAuthenticationError":
        return "O SIAFE-Rio recusou a autenticação. Confira as credenciais do .env."
    return (
        "Ocorreu uma falha inesperada durante a consulta ou o cálculo. "
        "Consulte o terminal do servidor sem compartilhar credenciais."
    )


# =============================================================================
# 8. DASHBOARD STREAMLIT
# =============================================================================

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
          <p>Consulta direta ao Flexvision, recálculo dos dados brutos e memória completa do mínimo de 25%.</p>
        </section>
        """
    )


def renderizar_metodologia_inicial() -> None:
    """Mostra um resumo do pipeline antes mesmo de haver uma consulta."""

    with st.expander("Entenda o fluxo dos dados e do cálculo", expanded=False):
        st.markdown(
            f"""
1. A consulta **{CONSULTA_RECEITAS}** fornece os componentes da receita prevista e arrecadada.
2. O Python soma esses componentes e calcula **25% da receita arrecadada** para a avaliação do período.
3. A consulta **{CONSULTA_DESPESAS}** fornece despesas e todos os insumos brutos dos redutores.
4. Os redutores **A, B, C e D** são calculados no Python, separadamente para cada estágio.
5. A aplicação é: **valores positivos − A − B − C − D − outras deduções**.
6. O índice é: **aplicação do estágio ÷ receita arrecadada × 100**.

O app não lê CSV e não usa um resultado previamente consolidado pelo Flexvision.
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
    """Consulta somente no clique e reaproveita o resultado na sessão atual.

    Streamlit reexecuta este arquivo a cada interação. O ``session_state`` evita
    uma nova chamada ao trocar apenas o estágio. O resultado só é reutilizado
    se ano, período, IDs das consultas e versão do cálculo permanecerem iguais.
    """

    # A chave é a identidade completa do snapshot. Alterar qualquer componente
    # faz o app pedir uma nova consulta em vez de exibir dados de outro contexto.
    chave_atual = (exercicio, periodo, CONSULTA_RECEITAS, CONSULTA_DESPESAS, VERSAO_CALCULO)
    consultar = st.button("Consultar / atualizar API", type="primary", icon="🔄")

    if consultar:
        # Se a atualização falhar, um resultado antigo não deve continuar na tela.
        st.session_state.pop("app_edu_resultado", None)
        try:
            with st.spinner(
                f"Consultando {CONSULTA_RECEITAS} e {CONSULTA_DESPESAS} — "
                f"{exercicio}/{periodo:02d}..."
            ):
                payload_parte1, payload_parte2 = buscar_dados_api(exercicio, periodo)
                parte1 = calcular_parte1(payload_parte1)
                parte2 = calcular_parte2(payload_parte2)
            st.session_state["app_edu_resultado"] = {
                "chave": chave_atual,
                "parte1": parte1,
                "parte2": parte2,
                "carregado_em": datetime.now().astimezone(),
            }
        except Exception as erro:
            st.error("Não foi possível consultar e calcular o índice.", icon="🚫")
            with st.expander("Ver diagnóstico seguro"):
                st.write(diagnostico_seguro(erro).replace("$", r"\$"))
            return None

    resultado = st.session_state.get("app_edu_resultado")
    if isinstance(resultado, dict) and resultado.get("chave") == chave_atual:
        return resultado

    st.info(
        "Escolha o exercício e o período e clique em **Consultar / atualizar API**. "
        "As credenciais são lidas do `.env` e nunca aparecem na página.",
        icon="ℹ️",
    )
    return None


def renderizar_contexto(
    resultado: dict[str, Any], exercicio: int, periodo: int, estagio: str
) -> None:
    """Exibe a referência temporal, IDs usados e ressalva de interpretação."""

    horario = resultado["carregado_em"].strftime("%d/%m/%Y %H:%M:%S %z")
    st.html(
        '<span class="contexto-educacao">'
        f"API Flexvision • {exercicio}/{periodo:02d} • consultas "
        f"{CONSULTA_RECEITAS} + {CONSULTA_DESPESAS} • carregado em {horario}"
        "</span>"
    )
    st.caption(
        f"Situação no estágio **{ESTAGIOS[estagio]}**. A escolha do estágio é "
        "analítica e não constitui conclusão jurídica."
    )
    for aviso in resultado["parte1"]["avisos"]:
        st.warning(aviso, icon="⚠️")


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


def main() -> None:
    """Orquestra a página na mesma ordem em que o usuário a lê."""

    st.set_page_config(
        page_title="Índice Constitucional da Educação",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    # 1) Contextualiza; 2) coleta filtros; 3) consulta/calcula; 4) apresenta.
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


if __name__ == "__main__":
    main()
