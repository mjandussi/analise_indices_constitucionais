"""Normalização de textos, números e formatos de resposta do Flexvision."""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


ZERO = Decimal("0")
CENTAVO = Decimal("0.01")


def normalizar_texto(valor: Any) -> str:
    """Gera uma chave textual estável sem acentos, caixa ou espaços repetidos."""

    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = texto.upper().replace("\xa0", " ")
    return " ".join(texto.split())


def numero_decimal(valor: Any, *, vazio_como_zero: bool = True) -> Decimal:
    """Converte número brasileiro ou formato numérico da API para ``Decimal``.

    São aceitos, entre outros, ``5.194.807.180,76``, ``5194807180.76``,
    ``R$ 1.234,56``, valores negativos e percentuais. Nenhum cálculo passa por
    ``float``.
    """

    if isinstance(valor, Decimal):
        return valor
    if valor is None or _valor_ausente(valor):
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

    texto = str(valor).strip().replace("\xa0", " ")
    if not texto or normalizar_texto(texto) in {"NAN", "NONE", "NULL", "N/A", "-"}:
        if vazio_como_zero:
            return ZERO
        raise ValueError("Valor numérico ausente.")

    negativo_parenteses = texto.startswith("(") and texto.endswith(")")
    texto = texto.replace("R$", "").replace("%", "").replace(" ", "")
    texto = re.sub(r"[^0-9,.+\-]", "", texto)
    negativo_final = texto.endswith("-")
    texto = texto.rstrip("-")

    if "," in texto and "." in texto:
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


def quantizar_moeda(valor: Decimal) -> Decimal:
    """Arredonda uma grandeza monetária para centavos (meio para cima)."""

    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def formatar_brl(valor: Decimal | None) -> str:
    """Formata um ``Decimal`` como moeda brasileira para uso no dashboard."""

    if valor is None:
        return "—"
    numero = f"{quantizar_moeda(valor):,.2f}"
    numero = numero.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {numero}"


def formatar_percentual(valor: Decimal | None, casas: int = 2) -> str:
    """Formata um percentual já expresso na escala 0–100."""

    if valor is None:
        return "—"
    passo = Decimal(1).scaleb(-casas)
    numero = f"{valor.quantize(passo, rounding=ROUND_HALF_UP):.{casas}f}"
    return numero.replace(".", ",") + "%"


def _valor_ausente(valor: Any) -> bool:
    try:
        comparacao = valor != valor
        return isinstance(comparacao, bool) and comparacao
    except (TypeError, ValueError):
        return False
