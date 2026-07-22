"""Configurações portáteis do projeto oficial do índice de educação."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

# Consultas Flexvision usadas pela extração.
CONSULTA_RECEITAS = "084835"
CONSULTA_DESPESAS = "084837"

# Parâmetros financeiros e estágios compartilhados pelas demais camadas.
META_CONSTITUCIONAL = Decimal("25")
REAJUSTE_TOTAL_2026 = Decimal("0.1156")
ESTAGIOS = {
    "dotacao_atual": "Dotação Atual",
    "despesa_autorizada": "Despesa Autorizada",
    "despesa_empenhada": "Despesa Empenhada",
    "despesa_liquidada": "Despesa Liquidada",
    "despesa_paga": "Despesa Paga",
}
ESTAGIOS_COMPARACAO = (
    "despesa_empenhada",
    "despesa_liquidada",
    "despesa_paga",
)

# Arquivos e diretórios são resolvidos a partir desta pasta, não do diretório
# em que o comando foi executado.
PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_ENV = PASTA_PROJETO / ".env"
PASTA_DADOS_EXTRAIDOS = PASTA_PROJETO / "dados_extraidos"
