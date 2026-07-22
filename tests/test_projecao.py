"""Testes da projeção anual de aplicação em educação."""

from __future__ import annotations

import unittest
from decimal import Decimal

from indices_constitucionais.erros import ErroRegraNegocio
from indices_constitucionais.projecao import (
    HISTORICO_OFICIAL_INDICE,
    NOMES_MESES,
    calcular_monitor_meta,
)


def parte2_sintetica() -> dict[str, object]:
    return {
        "total_aplicado": {"despesa_liquidada": Decimal("100.00")},
        "valores_positivos": {"despesa_liquidada": Decimal("130.00")},
        "total_fundeb": {
            "valores": {"despesa_liquidada": Decimal("80.00")}
        },
        "outras_deducoes": {"despesa_liquidada": Decimal("10.00")},
        "redutor_a": {"despesa_liquidada": Decimal("5.00")},
        "redutor_b": {"despesa_liquidada": Decimal("15.00")},
        "redutor_c": {"despesa_liquidada": Decimal("0.00")},
        "redutor_d": {"despesa_liquidada": Decimal("0.00")},
    }


def parte2_abril_homologada() -> dict[str, object]:
    return {
        "total_aplicado": {"despesa_liquidada": Decimal("6037355107.77")},
        "valores_positivos": {
            "despesa_liquidada": Decimal("6208296729.18")
        },
        "total_fundeb": {
            "valores": {"despesa_liquidada": Decimal("4746950289.79")}
        },
        "outras_deducoes": {
            "despesa_liquidada": Decimal("112563686.12")
        },
        "redutor_a": {"despesa_liquidada": Decimal("0.00")},
        "redutor_b": {"despesa_liquidada": Decimal("58377935.29")},
        "redutor_c": {"despesa_liquidada": Decimal("0.00")},
        "redutor_d": {"despesa_liquidada": Decimal("0.00")},
    }


class TestCalcularMonitorMeta(unittest.TestCase):
    def test_expoe_historico_e_meses_do_monitor(self) -> None:
        self.assertEqual(len(NOMES_MESES), 12)
        self.assertEqual(NOMES_MESES[0], "Janeiro")
        self.assertEqual(NOMES_MESES[-1], "Dezembro")
        self.assertEqual(
            HISTORICO_OFICIAL_INDICE,
            (
                {"ano": 2022, "indice": Decimal("25.70")},
                {"ano": 2023, "indice": Decimal("26.40")},
                {"ano": 2024, "indice": Decimal("26.94")},
                {"ano": 2025, "indice": Decimal("26.87")},
            ),
        )

    def test_projeta_mde_fundeb_e_reajuste_automatico(self) -> None:
        parte1 = {
            "base_arrecadada": Decimal("400.00"),
            "fundeb_realizado": Decimal("80.00"),
            "fundeb_previsto": Decimal("240.00"),
        }

        monitor = calcular_monitor_meta(
            parte1,
            parte2_sintetica(),
            4,
            base_anual_estimada=Decimal("1000.00"),
            meta_percentual=Decimal("25"),
            percentual_reajuste=Decimal("10.00"),
            mes_inicio_reajuste=7,
        )

        self.assertEqual(monitor["valor_meta"], Decimal("250.00"))
        self.assertEqual(monitor["mde_impostos_atual"], Decimal("40.00"))
        self.assertEqual(monitor["media_mensal_mde"], Decimal("10.00"))
        self.assertEqual(monitor["mde_futura_estimada"], Decimal("80.00"))
        self.assertEqual(monitor["fundeb_anual_projetado"], Decimal("240.00"))
        self.assertEqual(
            monitor["saldo_fundeb_ate_dezembro"], Decimal("160.00")
        )
        self.assertEqual(monitor["meses_com_reajuste"], 6)
        self.assertEqual(
            monitor["base_automatica_reajuste"], Decimal("60.00")
        )
        self.assertEqual(monitor["acrescimo_reajuste"], Decimal("6.00"))
        self.assertEqual(monitor["aplicacao_projetada"], Decimal("346.00"))
        self.assertEqual(monitor["indice_projetado"], Decimal("34.60"))
        self.assertEqual(monitor["situacao"], "Confortável")

    def test_projeta_numeros_homologados_de_abril_sem_dupla_contagem(self) -> None:
        parte1 = {
            "base_arrecadada": Decimal("25852525422.83"),
            "fundeb_previsto": Decimal("12262498170.86"),
            "fundeb_realizado": Decimal("4746950289.79"),
        }
        argumentos = {
            "parte1": parte1,
            "parte2": parte2_abril_homologada(),
            "periodo": 4,
            "base_anual_estimada": Decimal("68954885139.67"),
            "meta_percentual": Decimal("25"),
        }

        sem_reajuste = calcular_monitor_meta(**argumentos)
        com_reajuste = calcular_monitor_meta(
            **argumentos,
            percentual_reajuste=Decimal("11.56"),
            mes_inicio_reajuste=7,
        )

        self.assertEqual(
            sem_reajuste["mde_impostos_atual"], Decimal("1348782753.27")
        )
        self.assertEqual(
            sem_reajuste["fundeb_atual"], Decimal("4746950289.79")
        )
        self.assertEqual(
            sem_reajuste["saldo_fundeb_ate_dezembro"],
            Decimal("7515547881.07"),
        )
        self.assertEqual(
            sem_reajuste["aplicacao_projetada"], Decimal("16250468495.38")
        )
        self.assertEqual(com_reajuste["meses_com_reajuste"], 6)
        self.assertEqual(
            com_reajuste["base_automatica_reajuste"],
            Decimal("2023174129.91"),
        )
        self.assertEqual(
            com_reajuste["acrescimo_reajuste"], Decimal("233878929.42")
        )
        self.assertEqual(
            com_reajuste["aplicacao_projetada"], Decimal("16484347424.80")
        )

    def test_estima_fundeb_por_media_quando_parte1_nao_traz_previsao(self) -> None:
        parte1 = {"base_arrecadada": Decimal("25852525422.83")}

        monitor = calcular_monitor_meta(
            parte1,
            parte2_abril_homologada(),
            4,
            base_anual_estimada=Decimal("68954885139.67"),
            meta_percentual=Decimal("25"),
        )

        self.assertTrue(monitor["fundeb_estimado_por_media"])
        self.assertEqual(
            monitor["fundeb_anual_projetado"], Decimal("14240850869.37")
        )
        self.assertEqual(
            monitor["saldo_fundeb_ate_dezembro"], Decimal("9493900579.58")
        )

    def test_rejeita_parametros_invalidos(self) -> None:
        argumentos = {
            "parte1": {
                "base_arrecadada": Decimal("40.00"),
                "fundeb_previsto": Decimal("0.00"),
                "fundeb_realizado": Decimal("0.00"),
            },
            "parte2": {
                "total_aplicado": {"despesa_liquidada": Decimal("20.00")},
                "valores_positivos": {"despesa_liquidada": Decimal("20.00")},
                "total_fundeb": {
                    "valores": {"despesa_liquidada": Decimal("0.00")}
                },
                "outras_deducoes": {"despesa_liquidada": Decimal("0.00")},
                "redutor_a": {"despesa_liquidada": Decimal("0.00")},
                "redutor_b": {"despesa_liquidada": Decimal("0.00")},
                "redutor_c": {"despesa_liquidada": Decimal("0.00")},
                "redutor_d": {"despesa_liquidada": Decimal("0.00")},
            },
            "periodo": 6,
            "base_anual_estimada": Decimal("100.00"),
            "meta_percentual": Decimal("25"),
        }
        casos = (
            ({"periodo": 0}, "Período inválido no monitor: 0"),
            ({"base_anual_estimada": Decimal("0")}, "maior que zero"),
            ({"meta_percentual": Decimal("24.9")}, "inferior a 25"),
            ({"percentual_reajuste": Decimal("-1")}, "entre 0% e 100%"),
            ({"percentual_reajuste": Decimal("101")}, "entre 0% e 100%"),
            (
                {
                    "percentual_reajuste": Decimal("10"),
                    "mes_inicio_reajuste": 13,
                },
                "entre 1 e 12",
            ),
        )

        for alteracoes, mensagem in casos:
            with self.subTest(alteracoes=alteracoes):
                with self.assertRaisesRegex(ErroRegraNegocio, mensagem):
                    calcular_monitor_meta(**{**argumentos, **alteracoes})

    def test_rejeita_inconsistencias_nos_totais(self) -> None:
        parte1 = {
            "base_arrecadada": Decimal("400.00"),
            "fundeb_realizado": Decimal("80.02"),
            "fundeb_previsto": Decimal("240.00"),
        }
        with self.assertRaisesRegex(ErroRegraNegocio, "FUNDEB realizado"):
            calcular_monitor_meta(
                parte1,
                parte2_sintetica(),
                4,
                base_anual_estimada=Decimal("1000.00"),
                meta_percentual=Decimal("25"),
            )

        parte1["fundeb_realizado"] = Decimal("80.00")
        parte2 = parte2_sintetica()
        parte2["total_aplicado"] = {
            "despesa_liquidada": Decimal("100.02")
        }
        with self.assertRaisesRegex(ErroRegraNegocio, "decomposição"):
            calcular_monitor_meta(
                parte1,
                parte2,
                4,
                base_anual_estimada=Decimal("1000.00"),
                meta_percentual=Decimal("25"),
            )


if __name__ == "__main__":
    unittest.main()
