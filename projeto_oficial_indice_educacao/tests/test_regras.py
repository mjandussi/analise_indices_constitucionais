"""Teste didático: da consulta adaptada ao índice, como no Excel."""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

import pandas as pd


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dados import (  # noqa: E402
    calcular_metricas,
    preparar_parte1,
    preparar_parte2,
    processar_csvs,
)
from regras.calculos import calcular_parte1, calcular_parte2  # noqa: E402


COLUNAS = (
    "Dotação Atual",
    "Despesa Autorizada",
    "Despesa Empenhada",
    "Despesa Liquidada",
    "Despesa Paga",
)


def linha(descricao: str, valor: int) -> dict[str, object]:
    """Repete um valor nos cinco estágios para facilitar a conferência."""

    return {"Descrição": descricao, **{coluna: valor for coluna in COLUNAS}}


def parte1_adaptada() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Descrição": "(+) Impostos",
                "Receita Prevista (A)": "1.200,00",
                "Receita Arrecadada (B)": "900,00",
                "Diferença (B-A)": "-300,00",
                "Arrecadada/Prevista": "75,00",
            },
            {
                "Descrição": "(-) Transferências aos Municípios",
                "Receita Prevista (A)": "-200,00",
                "Receita Arrecadada (B)": "-100,00",
                "Diferença (B-A)": "100,00",
                "Arrecadada/Prevista": "50,00",
            },
            {
                "Descrição": "TOTAL - BASE DE CÁLCULO",
                "Receita Prevista (A)": "1.000,00",
                "Receita Arrecadada (B)": "800,00",
                "Diferença (B-A)": "-200,00",
                "Arrecadada/Prevista": "80,00",
            },
            {
                "Descrição": "VALOR A SER APLICADO EM EDUCAÇÃO (25%)",
                "Receita Prevista (A)": "250,00",
                "Receita Arrecadada (B)": "200,00",
                "Diferença (B-A)": "-50,00",
                "Arrecadada/Prevista": "80,00",
            },
        ]
    )


def parte2_adaptada() -> pd.DataFrame:
    return pd.DataFrame(
        [
            linha("(+) Fonte 100", 1000),
            linha("(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO", -100),

            # A = (100 - 40) + (50 - 20) = 90
            linha(
                "A - SUPERAVIT FINANCEIRO DOS RECURSOS TRANSFERIDOS DO "
                "FUNDEB-IMPOSTOS E TRANSF DE IMPOSTOS",
                100,
            ),
            linha(
                "A - APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO "
                "ANTERIOR-IMPOSTOS E TRANSF DE IMPOSTOS",
                40,
            ),
            linha(
                "A - SUPERAVIT FINANCEIRO DOS RECURSOS TRANSFERIDOS DO "
                "FUNDEB-COMPLEMENTAÇÃO DA UNIÃO",
                50,
            ),
            linha(
                "A - APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO "
                "ANTERIOR-COMPLEMENTAÇÃO DA UNIÃO",
                20,
            ),

            # B = 200 - 150 - 10% de 200 = 30
            linha("B - RECEITAS RECEBIDAS DO FUNDEB", 200),
            linha(
                "B - TOTAL DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB "
                "RECEBIDAS NO EXERCÍCIO",
                150,
            ),

            # C = max(80 - 20, 0) + max(30 - 50, 0) = 60
            linha("D - Restos a Pagar Cancelados (RPP e RPNP) em 2025", 80),
            linha("D - EXCESSO APLICADO EM EDUCAÇÃO em 2025", 20),
            linha("D - Restos a Pagar Cancelados (RPP e RPNP) em 2024", 30),
            linha("D - EXCESSO APLICADO EM EDUCAÇÃO em 2024", 50),

            # D = 10 + 5 = 15
            linha("C - RP Cancelado TAC - Inscritos em 2016", 10),
            linha("C - RP Cancelado TAC - Inscritos em 2017", 5),

            linha("(-) Outra despesa não computável", 25),
        ]
    )


class TestRegrasComoPlanilha(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parte1 = calcular_parte1(preparar_parte1(parte1_adaptada()))
        cls.parte2 = calcular_parte2(preparar_parte2(parte2_adaptada()))

    def test_parte1_apenas_le_os_totais_prontos(self) -> None:
        tabela = parte1_adaptada()
        tabela.loc[0, "Receita Prevista (A)"] = "9.999,00"
        tabela.loc[0, "Receita Arrecadada (B)"] = "8.888,00"
        resultado = calcular_parte1(preparar_parte1(tabela))

        # Mesmo com um componente diferente, valem as duas linhas prontas.
        self.assertEqual(resultado["base_prevista"], Decimal("1000.00"))
        self.assertEqual(resultado["base_arrecadada"], Decimal("800.00"))
        self.assertEqual(resultado["minimo_previsto"], Decimal("250.00"))
        self.assertEqual(resultado["minimo_arrecadado"], Decimal("200.00"))

    def test_parte2_calcula_as_linhas_que_faltavam(self) -> None:
        self.assertEqual(
            self.parte2["total_fundeb"]["valores"]["despesa_liquidada"],
            Decimal("100.00"),
        )
        esperados = {
            "redutor_a": Decimal("90.00"),
            "redutor_b": Decimal("30.00"),
            "redutor_c": Decimal("60.00"),
            "redutor_d": Decimal("15.00"),
        }
        for redutor, valor in esperados.items():
            self.assertEqual(self.parte2[redutor]["despesa_liquidada"], valor)

        tabela = pd.DataFrame(self.parte2["tabela_calculada"])
        esperado = [
            ("(+) Fonte 100", Decimal("1000.00")),
            (
                "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
                Decimal("100.00"),
            ),
            (
                "(-) SUPERÁVIT PERMITIDO NO EXERCÍCIO IMEDIATAMENTE ANTERIOR "
                "NÃO APLICADO ATÉ O PRIMEIRO QUADRIMESTRE DO EXERCÍCIO ATUAL",
                Decimal("90.00"),
            ),
            (
                "(-) RECEITAS DO FUNDEB NÃO UTILIZADAS NO EXERCÍCIO, "
                "EM VALOR SUPERIOR A 10%",
                Decimal("30.00"),
            ),
            ("(-) Outra despesa não computável", Decimal("25.00")),
            ("(-) Restos a Pagar Cancelados (I) - (II)", Decimal("75.00")),
            ("(I) Total dos Restos a Pagar Cancelados - MDE", Decimal("60.00")),
            (
                "(II) Restos a Pagar Cancelados - item 5.3.1 do TAC - "
                "(Ação Civil Pública 0054872- 30.2018.8.19.0001)",
                Decimal("15.00"),
            ),
            ("VALOR TOTAL DESTINADO A APLICAÇÃO EM EDUCAÇÃO (II)", Decimal("880.00")),
        ]
        obtido = list(zip(tabela["descricao"], tabela["despesa_liquidada"]))
        self.assertEqual(obtido, esperado)
        self.assertFalse(
            tabela["descricao"]
            .str.startswith(("A -", "B -", "C -", "D -"))
            .any()
        )

    def test_total_e_a_soma_dos_positivos_menos_os_negativos(self) -> None:
        tabela = pd.DataFrame(self.parte2["tabela_calculada"])
        descricao = tabela["descricao"]
        positivos = tabela[descricao.str.startswith("(+)")]["despesa_liquidada"].sum()
        negativos = tabela[descricao.str.startswith("(-)")]["despesa_liquidada"].sum()

        self.assertEqual(positivos, Decimal("1100.00"))
        self.assertEqual(negativos, Decimal("220.00"))
        self.assertEqual(positivos - negativos, Decimal("880.00"))
        self.assertEqual(
            self.parte2["total_aplicado"]["despesa_liquidada"],
            Decimal("880.00"),
        )
        self.assertEqual(
            tabela.iloc[-1]["despesa_liquidada"], Decimal("880.00")
        )

        metricas = calcular_metricas(
            self.parte1, self.parte2, "despesa_liquidada"
        )
        self.assertEqual(metricas["indice_periodo"], Decimal("110.0"))

    def test_faz_a_mesma_conta_nos_cinco_estagios(self) -> None:
        tabela = parte2_adaptada()
        for fator, coluna in enumerate(COLUNAS, start=1):
            tabela[coluna] = tabela[coluna] * fator

        resultado = calcular_parte2(preparar_parte2(tabela))
        self.assertEqual(
            resultado["total_aplicado"],
            {
                "dotacao_atual": Decimal("880.00"),
                "despesa_autorizada": Decimal("1760.00"),
                "despesa_empenhada": Decimal("2640.00"),
                "despesa_liquidada": Decimal("3520.00"),
                "despesa_paga": Decimal("4400.00"),
            },
        )

    def test_aceita_o_fundeb_positivo_mostrado_na_planilha_adaptada(self) -> None:
        tabela = parte2_adaptada()
        linha_fundeb = tabela["Descrição"].str.contains("FUNDEB-FILTRO")
        tabela.loc[linha_fundeb, "Descrição"] = (
            "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
        )
        tabela.loc[linha_fundeb, list(COLUNAS)] = 100

        resultado = calcular_parte2(preparar_parte2(tabela))
        self.assertEqual(
            resultado["total_aplicado"]["despesa_liquidada"],
            Decimal("880.00"),
        )

    def test_nao_duplica_fundeb_direto_e_filtro(self) -> None:
        tabela = pd.concat(
            [
                parte2_adaptada(),
                pd.DataFrame(
                    [linha("(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB", 100)]
                ),
            ],
            ignore_index=True,
        )

        resultado = calcular_parte2(preparar_parte2(tabela))
        self.assertEqual(
            resultado["valores_positivos"]["despesa_liquidada"],
            Decimal("1100.00"),
        )
        self.assertEqual(
            resultado["total_aplicado"]["despesa_liquidada"],
            Decimal("880.00"),
        )

    def test_nao_duplica_linhas_consolidadas_antigas(self) -> None:
        antigas = [
            linha(
                "(-) SUPERÁVIT PERMITIDO NO EXERCÍCIO IMEDIATAMENTE ANTERIOR "
                "NÃO APLICADO ATÉ O PRIMEIRO QUADRIMESTRE DO EXERCÍCIO ATUAL",
                999,
            ),
            linha(
                "(-) RECEITAS DO FUNDEB NÃO UTILIZADAS NO EXERCÍCIO, "
                "EM VALOR SUPERIOR A 10%",
                999,
            ),
            linha("(-) Restos a Pagar Cancelados (I) - (II)", 999),
        ]
        tabela = pd.concat(
            [parte2_adaptada(), pd.DataFrame(antigas)], ignore_index=True
        )

        resultado = calcular_parte2(preparar_parte2(tabela))
        self.assertEqual(
            resultado["total_aplicado"]["despesa_liquidada"],
            Decimal("880.00"),
        )

    def test_resultado_real_de_abril_de_2026(self) -> None:
        resultado = processar_csvs(RAIZ / "tests" / "fixtures" / "abril_2026")
        parte1 = resultado["parte1"]
        parte2 = resultado["parte2"]

        self.assertEqual(parte1["base_arrecadada"], Decimal("25852525422.83"))
        self.assertEqual(
            parte2["total_aplicado"],
            {
                "dotacao_atual": Decimal("10652809036.97"),
                "despesa_autorizada": Decimal("9735697854.66"),
                "despesa_empenhada": Decimal("6276741394.65"),
                "despesa_liquidada": Decimal("6037355107.77"),
                "despesa_paga": Decimal("5915601500.84"),
            },
        )
        metricas = calcular_metricas(parte1, parte2, "despesa_liquidada")
        self.assertEqual(
            metricas["indice_periodo"].quantize(Decimal("0.01")),
            Decimal("23.35"),
        )


if __name__ == "__main__":
    unittest.main()
