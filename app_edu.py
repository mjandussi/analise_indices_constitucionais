"""Ponto de entrada compatível do dashboard de educação.

O código foi separado na pasta :mod:`app_educacao`:

* ``extracao.py`` consulta o Flexvision e gera os dois CSVs;
* ``dados.py`` lê os CSVs e executa a ETL/cálculos;
* ``dash_indice.py`` apresenta o índice atual; e
* ``dash_projecao.py`` apresenta o monitor anual.

As importações abaixo preservam os nomes usados por testes e scripts antigos.
"""

from __future__ import annotations

from typing import Any

from app_educacao.apresentacao import (
    formatar_brl_compacto,
    formula_monetaria,
    linha_financeira,
    quadro_formacao_aplicacao,
    relatorio_calculado,
)
from app_educacao.config import (
    CONSULTA_DESPESAS,
    CONSULTA_RECEITAS,
    ESTAGIOS,
    ESTAGIOS_COMPARACAO,
    META_CONSTITUCIONAL,
    REAJUSTE_TOTAL_2026,
    VERSAO_CALCULO,
)
from app_educacao.dados import (
    CENTAVO,
    ZERO,
    ErroDadosEducacao,
    calcular_metricas,
    calcular_parte1,
    calcular_parte2,
    calcular_todos_os_indices,
    formatar_brl,
    formatar_percentual,
    minimo_25_por_cento,
    moeda,
    normalizar_texto,
    para_decimal,
    percentual,
    processar_snapshot,
)
from app_educacao.extracao import (
    extrair_dados_educacao,
    extrair_e_persistir_dados_educacao,
    ler_credenciais,
    localizar_snapshot,
)
from indices_constitucionais.erros import ErroConsultaFlexvision
from indices_constitucionais.normalizacao import extrair_registros
from indices_constitucionais.projecao import (
    HISTORICO_OFICIAL_INDICE,
    NOMES_MESES,
    calcular_monitor_meta,
)


def buscar_dados_api(exercicio: int, periodo: int) -> tuple[Any, Any]:
    """Compatibilidade: retorna os dois payloads JSON sem persistir arquivos."""

    dados = extrair_dados_educacao(exercicio, periodo)
    return dados["parte1"], dados["parte2"]


def main() -> None:
    """Executa o dashboard principal; a importação é tardia e sem efeitos colaterais."""

    from app_educacao.dash_indice import main as executar_dashboard

    # O launcher histórico mantém as duas áreas na mesma página. Cada dashboard
    # também pode ser executado isoladamente pelos arquivos da nova pasta.
    executar_dashboard(incluir_projecao=True)


if __name__ == "__main__":
    main()
