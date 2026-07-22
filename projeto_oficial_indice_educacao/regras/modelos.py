"""Objetos de resultado estáveis para consumo pelo Streamlit."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .erros import ErroRegraNegocio
from .normalizacao import ZERO, normalizar_texto, quantizar_moeda


ESTAGIOS_DESPESA = (
    "dotacao_atual",
    "despesa_autorizada",
    "despesa_empenhada",
    "despesa_liquidada",
    "despesa_paga",
)

ROTULOS_ESTAGIOS = {
    "dotacao_atual": "Dotação atual",
    "despesa_autorizada": "Despesa autorizada",
    "despesa_empenhada": "Despesa empenhada",
    "despesa_liquidada": "Despesa liquidada",
    "despesa_paga": "Despesa paga",
}


@dataclass(frozen=True)
class ResultadoParte1:
    base_prevista: Decimal
    base_arrecadada: Decimal
    diferenca_receita: Decimal
    realizacao_percentual: Decimal | None
    minimo_sobre_prevista: Decimal
    minimo_sobre_arrecadada: Decimal
    diferenca_minimo: Decimal
    componentes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    avisos: tuple[str, ...] = field(default_factory=tuple)
    fundeb_previsto: Decimal | None = None
    fundeb_realizado: Decimal | None = None

    def __post_init__(self) -> None:
        if self.base_prevista < ZERO or self.base_arrecadada < ZERO:
            raise ErroRegraNegocio(
                "As bases prevista e arrecadada da educação não podem ser negativas."
            )

    def metricas(self) -> dict[str, Decimal | None]:
        return {
            "base_prevista": self.base_prevista,
            "base_arrecadada": self.base_arrecadada,
            "diferenca_receita": self.diferenca_receita,
            "realizacao_percentual": self.realizacao_percentual,
            "minimo_sobre_prevista": self.minimo_sobre_prevista,
            "minimo_sobre_arrecadada": self.minimo_sobre_arrecadada,
            "diferenca_minimo": self.diferenca_minimo,
            "fundeb_previsto": self.fundeb_previsto,
            "fundeb_realizado": self.fundeb_realizado,
        }


@dataclass(frozen=True)
class ResultadoParte2:
    valores_positivos: dict[str, Decimal]
    redutor_a: dict[str, Decimal]
    redutor_b: dict[str, Decimal]
    redutor_c: dict[str, Decimal]
    redutor_d: dict[str, Decimal]
    outras_deducoes: dict[str, Decimal]
    total_aplicado: dict[str, Decimal]
    detalhes_a: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    detalhes_c: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    linhas_normalizadas: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    total_fundeb: dict[str, Any] | None = None
    origem_total_fundeb: str | None = None
    detalhes_b: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    detalhes_d: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    linhas_positivas: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    outras_linhas: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def valor(self, estagio: str = "despesa_liquidada") -> Decimal:
        validar_estagio(estagio)
        return self.total_aplicado[estagio]

    def quadro_resumo(self) -> list[dict[str, Any]]:
        series = (
            ("Valores positivos", self.valores_positivos),
            ("Redutor A — superávit", self.redutor_a),
            ("Redutor B — FUNDEB acima de 10%", self.redutor_b),
            ("Redutor C — RP cancelados MDE", self.redutor_c),
            ("Redutor D — RP cancelados TAC", self.redutor_d),
            ("Outras deduções", self.outras_deducoes),
            ("Total aplicado em educação", self.total_aplicado),
        )
        return [
            {"metrica": rotulo, **{estagio: valores[estagio] for estagio in ESTAGIOS_DESPESA}}
            for rotulo, valores in series
        ]

    def relatorio_calculado(self) -> list[dict[str, Any]]:
        """Monta o leiaute consolidado equivalente ao antigo relatório.

        As linhas brutas de A–D permanecem em ``linhas_normalizadas`` para
        auditoria. Nesta visão elas são substituídas pelos resultados das
        fórmulas, preservando as fontes positivas e as demais deduções na
        ordem em que chegaram.
        """

        positivas: list[dict[str, Any]] = []
        deducoes_ordinarias: list[dict[str, Any]] = []
        agregados_calculados = (
            "SUPERAVIT PERMITIDO NO EXERCICIO IMEDIATAMENTE ANTERIOR",
            "RECEITAS DO FUNDEB NAO UTILIZADAS NO EXERCICIO",
            "RESTOS A PAGAR CANCELADOS (I) - (II)",
        )

        for linha in self.linhas_normalizadas:
            descricao = str(linha.get("descricao", ""))
            chave = normalizar_texto(descricao).lstrip()
            registro = {
                "descricao": descricao,
                **{estagio: linha[estagio] for estagio in ESTAGIOS_DESPESA},
            }
            if (
                "FUNDEB" in chave and "FILTRO" in chave
            ):
                continue
            if chave.startswith("(+)"):
                positivas.append(registro)
            elif chave.startswith("(-)") and not any(
                agregado in chave for agregado in agregados_calculados
            ):
                deducoes_ordinarias.append(registro)

        redutor_c_d = {
            estagio: quantizar_moeda(
                self.redutor_c[estagio] + self.redutor_d[estagio]
            )
            for estagio in ESTAGIOS_DESPESA
        }

        def linha_calculada(
            descricao: str, valores: dict[str, Decimal]
        ) -> dict[str, Any]:
            return {
                "descricao": descricao,
                **{estagio: valores[estagio] for estagio in ESTAGIOS_DESPESA},
            }

        return [
            *positivas,
            linha_calculada(
                "(-) SUPERÁVIT PERMITIDO NO EXERCÍCIO IMEDIATAMENTE ANTERIOR "
                "NÃO APLICADO ATÉ O PRIMEIRO QUADRIMESTRE DO EXERCÍCIO ATUAL",
                self.redutor_a,
            ),
            linha_calculada(
                "(-) RECEITAS DO FUNDEB NÃO UTILIZADAS NO EXERCÍCIO, EM VALOR "
                "SUPERIOR A 10%",
                self.redutor_b,
            ),
            *deducoes_ordinarias,
            linha_calculada(
                "(-) Restos a Pagar Cancelados (I) - (II)",
                redutor_c_d,
            ),
            linha_calculada(
                "(I) Total dos Restos a Pagar Cancelados - MDE",
                self.redutor_c,
            ),
            linha_calculada(
                "(II) Restos a Pagar Cancelados - item 5.3.1 do TAC - "
                "(Ação Civil Pública 0054872- 30.2018.8.19.0001)",
                self.redutor_d,
            ),
            linha_calculada(
                "VALOR TOTAL DESTINADO A APLICAÇÃO EM EDUCAÇÃO (II)",
                self.total_aplicado,
            ),
        ]


@dataclass(frozen=True)
class ResultadoEducacao:
    parte1: ResultadoParte1
    parte2: ResultadoParte2
    estagio_indice: str = "despesa_liquidada"

    def __post_init__(self) -> None:
        validar_estagio(self.estagio_indice)

    def metricas_dashboard(self, estagio: str | None = None) -> dict[str, Any]:
        fase = estagio or self.estagio_indice
        validar_estagio(fase)
        aplicado = self.parte2.total_aplicado[fase]
        base_prevista = self.parte1.base_prevista
        base = self.parte1.base_arrecadada
        minimo_previsto = self.parte1.minimo_sobre_prevista
        minimo = self.parte1.minimo_sobre_arrecadada

        indice = aplicado * Decimal("100") / base if base else None
        indice_previsto = (
            aplicado * Decimal("100") / base_prevista if base_prevista else None
        )
        saldo = quantizar_moeda(aplicado - minimo)
        deficit = max(-saldo, ZERO)
        excedente = max(saldo, ZERO)
        saldo_previsto = quantizar_moeda(aplicado - minimo_previsto)
        deficit_previsto = max(-saldo_previsto, ZERO)
        excedente_previsto = max(saldo_previsto, ZERO)
        margem_pp = indice - Decimal("25") if indice is not None else None
        atingimento_minimo = aplicado * Decimal("100") / minimo if minimo else None
        atingimento_minimo_previsto = (
            aplicado * Decimal("100") / minimo_previsto if minimo_previsto else None
        )

        return {
            "estagio": fase,
            "receita_prevista": base_prevista,
            "receita_arrecadada": base,
            "realizacao_receita_percentual": self.parte1.realizacao_percentual,
            "minimo_constitucional_previsto": minimo_previsto,
            "minimo_constitucional": minimo,
            "aplicacao_educacao": aplicado,
            "indice_aplicacao_percentual": indice,
            "indice_sobre_receita_prevista_percentual": indice_previsto,
            "margem_pontos_percentuais": margem_pp,
            "saldo_para_minimo": saldo,
            "deficit_para_minimo": deficit,
            "excedente_sobre_minimo": excedente,
            "atingimento_do_minimo_percentual": atingimento_minimo,
            "atingiu_minimo": indice is not None and indice >= Decimal("25"),
            "saldo_para_minimo_previsto": saldo_previsto,
            "deficit_para_minimo_previsto": deficit_previsto,
            "excedente_sobre_minimo_previsto": excedente_previsto,
            "atingimento_do_minimo_previsto_percentual": atingimento_minimo_previsto,
            "atingiu_minimo_previsto": (
                minimo_previsto > ZERO and aplicado >= minimo_previsto
            ),
        }

    def metricas_por_estagio(self) -> list[dict[str, Any]]:
        return [self.metricas_dashboard(estagio) for estagio in ESTAGIOS_DESPESA]


def validar_estagio(estagio: str) -> None:
    if estagio not in ESTAGIOS_DESPESA:
        permitidos = ", ".join(ESTAGIOS_DESPESA)
        raise ErroRegraNegocio(
            f"Estágio de despesa inválido: {estagio!r}. Use um de: {permitidos}."
        )
