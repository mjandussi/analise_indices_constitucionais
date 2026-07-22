"""Regressões dos dados de FUNDEB e das memórias de auditoria."""

from __future__ import annotations

import unittest
from decimal import Decimal

from indices_constitucionais import (
    ESTAGIOS_DESPESA,
    ResultadoParte1,
    ResultadoParte2,
    calcular_parte1,
    calcular_parte2,
)
from tests.test_indices_constitucionais import (
    COLUNAS_PARTE2,
    _fixture_parte2_bruta,
)


class TestFundebParte1(unittest.TestCase):
    def test_campos_novos_tem_defaults_compativeis(self) -> None:
        resultado = ResultadoParte1(
            Decimal("100"),
            Decimal("80"),
            Decimal("-20"),
            Decimal("80"),
            Decimal("25"),
            Decimal("20"),
            Decimal("-5"),
        )

        self.assertIsNone(resultado.fundeb_previsto)
        self.assertIsNone(resultado.fundeb_realizado)

    def test_total_destinado_ao_fundeb_e_auditado_sem_entrar_na_base(self) -> None:
        dados = [
            {
                "Descrição": "(+) Impostos",
                "Receita Prevista": "100,00",
                "Receita Arrecadada": "80,00",
            },
            {
                "Descrição": "(-) Transferências aos Municípios",
                "Receita Prevista": "-20,00",
                "Receita Arrecadada": "-10,00",
            },
            {
                "Descrição": "5- TOTAL DESTINADO AO FUNDEB",
                "Receita Prevista": "12.262.498.170,86",
                "Receita Arrecadada": "4.746.950.289,79",
            },
            {
                "Descrição": "TOTAL - BASE DE CÁLCULO",
                "Receita Prevista": "80,00",
                "Receita Arrecadada": "70,00",
            },
        ]

        resultado = calcular_parte1(dados)

        self.assertEqual(resultado.base_prevista, Decimal("80.00"))
        self.assertEqual(resultado.base_arrecadada, Decimal("70.00"))
        self.assertEqual(len(resultado.componentes), 2)
        self.assertEqual(resultado.fundeb_previsto, Decimal("12262498170.86"))
        self.assertEqual(resultado.fundeb_realizado, Decimal("4746950289.79"))
        self.assertEqual(
            resultado.metricas()["fundeb_realizado"],
            Decimal("4746950289.79"),
        )


class TestAuditoriaParte2(unittest.TestCase):
    def test_campos_novos_tem_defaults_compativeis(self) -> None:
        serie = {estagio: Decimal("0") for estagio in ESTAGIOS_DESPESA}
        resultado = ResultadoParte2(
            serie,
            serie,
            serie,
            serie,
            serie,
            serie,
            serie,
        )

        self.assertIsNone(resultado.total_fundeb)
        self.assertIsNone(resultado.origem_total_fundeb)
        self.assertEqual(resultado.detalhes_b, {})
        self.assertEqual(resultado.detalhes_d, ())
        self.assertEqual(resultado.linhas_positivas, ())
        self.assertEqual(resultado.outras_linhas, ())

    def test_expoe_fundeb_linhas_e_memorias_completas_dos_redutores(self) -> None:
        dados = _fixture_parte2_bruta()
        for linha in dados:
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB" in str(
                linha["Descrição"]
            ):
                linha["Descrição"] = (
                    "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO"
                )
                for coluna in COLUNAS_PARTE2.values():
                    linha[coluna] = -50
                break

        resultado = calcular_parte2(dados, validar_total_final=False)

        self.assertIsNotNone(resultado.total_fundeb)
        assert resultado.total_fundeb is not None
        self.assertEqual(
            resultado.total_fundeb["valores"]["despesa_liquidada"],
            Decimal("50.00"),
        )
        self.assertEqual(
            resultado.origem_total_fundeb,
            "0 - linha FUNDEB-FILTRO",
        )
        self.assertTrue(
            any(
                linha["descricao"]
                == "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
                for linha in resultado.linhas_positivas
            )
        )
        self.assertFalse(
            any(
                "FUNDEB-FILTRO" in linha["descricao"]
                for linha in resultado.linhas_positivas
            )
        )
        self.assertEqual(len(resultado.outras_linhas), 1)

        detalhe_a = {
            item["grupo"]: item for item in resultado.detalhes_a
        }["complementacao_uniao"]
        self.assertEqual(
            detalhe_a["superavit"]["despesa_liquidada"], Decimal("80")
        )
        self.assertEqual(
            detalhe_a["aplicacao"]["despesa_liquidada"], Decimal("30")
        )
        self.assertEqual(
            detalhe_a["redutor"]["despesa_liquidada"], Decimal("50.00")
        )
        self.assertEqual(
            detalhe_a["despesa_liquidada"],
            detalhe_a["redutor"]["despesa_liquidada"],
        )

        self.assertEqual(
            resultado.detalhes_b["receita_fundeb"]["despesa_liquidada"],
            Decimal("500"),
        )
        self.assertEqual(
            resultado.detalhes_b["despesa_fundeb"]["despesa_liquidada"],
            Decimal("440"),
        )
        self.assertEqual(
            resultado.detalhes_b["valor_nao_aplicado"]["despesa_liquidada"],
            Decimal("60.00"),
        )
        self.assertEqual(
            resultado.detalhes_b["limite_dez_por_cento"]["despesa_liquidada"],
            Decimal("50.00"),
        )
        self.assertEqual(
            resultado.detalhes_b["redutor"],
            resultado.redutor_b,
        )

        detalhe_c = {
            item["ano"]: item for item in resultado.detalhes_c
        }[2025]
        self.assertEqual(
            detalhe_c["rp_cancelado"]["despesa_liquidada"], Decimal("90")
        )
        self.assertEqual(
            detalhe_c["excesso_aplicado"]["despesa_liquidada"], Decimal("40")
        )
        self.assertEqual(
            detalhe_c["redutor"]["despesa_liquidada"], Decimal("50.00")
        )
        self.assertEqual(detalhe_c["exercicio_inscricao"], detalhe_c["ano"])

        detalhes_d = {item["ano"]: item for item in resultado.detalhes_d}
        self.assertEqual(set(detalhes_d), {2016, 2017})
        self.assertEqual(
            detalhes_d[2017]["valores"]["despesa_liquidada"], Decimal("9")
        )
        self.assertEqual(
            resultado.redutor_d["despesa_liquidada"], Decimal("13.00")
        )


if __name__ == "__main__":
    unittest.main()
