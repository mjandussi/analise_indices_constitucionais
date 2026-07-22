"""Regressões da versão didática e API-only do dashboard de educação."""

from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import app_edu
from indices_constitucionais.fontes import ler_csv_parte1, ler_csv_parte2


RAIZ = Path(__file__).resolve().parents[1]
PASTA_CONSULTAS = RAIZ / "consultas_base"
STREAMLIT_DISPONIVEL = importlib.util.find_spec("streamlit") is not None


def arquivo_unico(padrao: str) -> Path:
    encontrados = list(PASTA_CONSULTAS.glob(padrao))
    if len(encontrados) != 1:
        raise AssertionError(f"Esperado um arquivo para {padrao}; encontrados {len(encontrados)}.")
    return encontrados[0]


ARQUIVO_PARTE1 = arquivo_unico("*Parte 1_3 (2026)_*.csv")
ARQUIVO_PARTE2 = arquivo_unico("*Parte 2_3 (2026) com FR 108 Adaptado_*.csv")


def fixture_parte2_no_formato_atual_da_api() -> list[dict[str, object]]:
    """Converte o CSV histórico no contrato atual: filtro negativo na última linha."""

    dados = deepcopy(ler_csv_parte2(ARQUIVO_PARTE2))
    coluna_descricao = next(iter(dados[0]))
    linha = next(
        item
        for item in dados
        if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
        in app_edu.normalizar_texto(item[coluna_descricao])
    )
    dados.remove(linha)
    linha[coluna_descricao] = "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO"
    for coluna in list(linha)[1:]:
        linha[coluna] = str(-app_edu.para_decimal(linha[coluna]))
    dados.append(linha)
    return dados


class TestCalculosAppEdu(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dados_parte1 = ler_csv_parte1(ARQUIVO_PARTE1)
        cls.dados_parte2 = fixture_parte2_no_formato_atual_da_api()

    def test_reproduz_resultado_homologado_de_abril_2026(self) -> None:
        parte1 = app_edu.calcular_parte1(self.dados_parte1)
        parte2 = app_edu.calcular_parte2(self.dados_parte2)
        metricas = app_edu.calcular_metricas(parte1, parte2, "despesa_liquidada")

        self.assertEqual(parte1["base_prevista"], Decimal("68954885139.67"))
        self.assertEqual(parte1["base_arrecadada"], Decimal("25852525422.83"))
        self.assertEqual(parte1["minimo_previsto"], Decimal("17238721284.92"))
        self.assertEqual(parte1["minimo_arrecadado"], Decimal("6463131355.71"))
        self.assertEqual(
            parte2["valores_positivos"]["despesa_liquidada"],
            Decimal("6208296729.18"),
        )
        self.assertEqual(parte2["redutor_a"]["despesa_liquidada"], Decimal("0.00"))
        self.assertEqual(
            parte2["redutor_b"]["despesa_liquidada"], Decimal("58377935.29")
        )
        self.assertEqual(parte2["redutor_c"]["despesa_liquidada"], Decimal("0.00"))
        self.assertEqual(parte2["redutor_d"]["despesa_liquidada"], Decimal("0.00"))
        self.assertEqual(
            parte2["outras_deducoes"]["despesa_liquidada"],
            Decimal("112563686.12"),
        )
        self.assertEqual(metricas["aplicado"], Decimal("6037355107.77"))
        self.assertEqual(metricas["deficit_periodo"], Decimal("425776247.94"))

    def test_no_fundeb_filtro_e_invertido_sem_dupla_contagem(self) -> None:
        dados = deepcopy(self.dados_parte2)

        parte2 = app_edu.calcular_parte2(dados)

        self.assertEqual(
            parte2["total_fundeb"]["valores"]["despesa_liquidada"],
            Decimal("4746950289.79"),
        )
        self.assertEqual(
            parte2["total_aplicado"]["despesa_liquidada"],
            Decimal("6037355107.77"),
        )
        self.assertEqual(
            parte2["origem_total_fundeb"], "0 - linha FUNDEB-FILTRO"
        )

    def test_fundeb_filtro_e_localizado_mesmo_fora_da_ultima_posicao(self) -> None:
        dados = deepcopy(self.dados_parte2)
        dados[-1], dados[-2] = dados[-2], dados[-1]

        parte2 = app_edu.calcular_parte2(dados)

        self.assertEqual(
            parte2["total_fundeb"]["valores"]["despesa_liquidada"],
            Decimal("4746950289.79"),
        )

    def test_configuracao_usa_somente_as_consultas_api_atuais(self) -> None:
        self.assertEqual(app_edu.CONSULTA_RECEITAS, "084835")
        self.assertEqual(app_edu.CONSULTA_DESPESAS, "084837")

    def test_monitor_projeta_mde_fundeb_e_reajuste_automatico(self) -> None:
        parte1 = {
            "base_arrecadada": Decimal("400.00"),
            "fundeb_realizado": Decimal("80.00"),
            "fundeb_previsto": Decimal("240.00"),
        }
        parte2 = {
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

        monitor = app_edu.calcular_monitor_meta(
            parte1,
            parte2,
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
        self.assertEqual(monitor["saldo_fundeb_ate_dezembro"], Decimal("160.00"))
        self.assertEqual(monitor["meses_com_reajuste"], 6)
        self.assertEqual(monitor["base_automatica_reajuste"], Decimal("60.00"))
        self.assertEqual(monitor["acrescimo_reajuste"], Decimal("6.00"))
        self.assertEqual(monitor["aplicacao_projetada"], Decimal("346.00"))
        self.assertEqual(monitor["indice_projetado"], Decimal("34.60"))
        self.assertEqual(monitor["situacao"], "Confortável")

    def test_monitor_projeta_numeros_homologados_de_abril_sem_dupla_contagem(self) -> None:
        parte1 = app_edu.calcular_parte1(self.dados_parte1)
        parte1["fundeb_previsto"] = Decimal("12262498170.86")
        parte1["fundeb_realizado"] = Decimal("4746950289.79")
        parte2 = app_edu.calcular_parte2(self.dados_parte2)

        sem_reajuste = app_edu.calcular_monitor_meta(
            parte1,
            parte2,
            4,
            base_anual_estimada=parte1["base_prevista"],
            meta_percentual=Decimal("25"),
        )
        com_reajuste = app_edu.calcular_monitor_meta(
            parte1,
            parte2,
            4,
            base_anual_estimada=parte1["base_prevista"],
            meta_percentual=Decimal("25"),
            percentual_reajuste=Decimal("11.56"),
            mes_inicio_reajuste=7,
        )

        self.assertEqual(
            sem_reajuste["mde_impostos_atual"], Decimal("1348782753.27")
        )
        self.assertEqual(sem_reajuste["fundeb_atual"], Decimal("4746950289.79"))
        self.assertEqual(
            sem_reajuste["saldo_fundeb_ate_dezembro"], Decimal("7515547881.07")
        )
        self.assertEqual(
            sem_reajuste["aplicacao_projetada"], Decimal("16250468495.38")
        )
        self.assertEqual(com_reajuste["meses_com_reajuste"], 6)
        self.assertEqual(
            com_reajuste["base_automatica_reajuste"], Decimal("2023174129.91")
        )
        self.assertEqual(
            com_reajuste["acrescimo_reajuste"], Decimal("233878929.42")
        )
        self.assertEqual(
            com_reajuste["aplicacao_projetada"], Decimal("16484347424.80")
        )

    def test_monitor_estima_fundeb_por_media_quando_parte1_nao_traz_previsao(self) -> None:
        parte1 = app_edu.calcular_parte1(self.dados_parte1)
        parte2 = app_edu.calcular_parte2(self.dados_parte2)

        monitor = app_edu.calcular_monitor_meta(
            parte1,
            parte2,
            4,
            base_anual_estimada=parte1["base_prevista"],
            meta_percentual=Decimal("25"),
        )

        self.assertTrue(monitor["fundeb_estimado_por_media"])
        self.assertEqual(
            monitor["fundeb_anual_projetado"], Decimal("14240850869.37")
        )
        self.assertEqual(
            monitor["saldo_fundeb_ate_dezembro"], Decimal("9493900579.58")
        )

    def test_monitor_rejeita_base_meta_percentual_e_mes_invalidos(self) -> None:
        parte1 = {
            "base_arrecadada": Decimal("40.00"),
            "fundeb_previsto": Decimal("0.00"),
            "fundeb_realizado": Decimal("0.00"),
        }
        parte2 = {
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
        }
        argumentos = {
            "parte1": parte1,
            "parte2": parte2,
            "periodo": 6,
            "base_anual_estimada": Decimal("100.00"),
            "meta_percentual": Decimal("25"),
        }
        with self.assertRaisesRegex(app_edu.ErroDadosEducacao, "maior que zero"):
            app_edu.calcular_monitor_meta(**{**argumentos, "base_anual_estimada": Decimal("0")})
        with self.assertRaisesRegex(app_edu.ErroDadosEducacao, "inferior a 25"):
            app_edu.calcular_monitor_meta(**{**argumentos, "meta_percentual": Decimal("24.9")})
        with self.assertRaisesRegex(app_edu.ErroDadosEducacao, "entre 0% e 100%"):
            app_edu.calcular_monitor_meta(
                **argumentos, percentual_reajuste=Decimal("-1")
            )
        with self.assertRaisesRegex(app_edu.ErroDadosEducacao, "entre 1 e 12"):
            app_edu.calcular_monitor_meta(
                **argumentos, percentual_reajuste=Decimal("10"), mes_inicio_reajuste=13
            )

    def test_parte1_captura_total_destinado_ao_fundeb_sem_somar_na_base(self) -> None:
        dados = deepcopy(self.dados_parte1)
        dados.append(
            {
                "descricao": "5- TOTAL DESTINADO AO FUNDEB",
                "Receita Prevista": "12.262.498.170,86",
                "Receita Arrecadada": "4.746.950.289,79",
                "Diferença (B-A)": "-7.515.547.881,07",
                "Arrecadada/Prevista": "38,71",
            }
        )

        parte1 = app_edu.calcular_parte1(dados)

        self.assertEqual(parte1["base_prevista"], Decimal("68954885139.67"))
        self.assertEqual(parte1["fundeb_previsto"], Decimal("12262498170.86"))
        self.assertEqual(parte1["fundeb_realizado"], Decimal("4746950289.79"))

    def test_linha_sem_coluna_de_descricao_nao_e_ignorada(self) -> None:
        dados_parte1 = deepcopy(self.dados_parte1)
        coluna_parte1 = next(iter(dados_parte1[0]))
        dados_parte1[0].pop(coluna_parte1)

        with self.assertRaisesRegex(app_edu.ErroDadosEducacao, "coluna de descrição"):
            app_edu.calcular_parte1(dados_parte1)

        dados_parte2 = deepcopy(self.dados_parte2)
        coluna_parte2 = next(iter(dados_parte2[0]))
        dados_parte2[0].pop(coluna_parte2)

        with self.assertRaisesRegex(app_edu.ErroDadosEducacao, "coluna de descrição"):
            app_edu.calcular_parte2(dados_parte2)


@unittest.skipUnless(STREAMLIT_DISPONIVEL, "Streamlit não instalado.")
class TestTelaAppEdu(unittest.TestCase):
    def test_abre_sem_csv_e_sem_consultar_api_automaticamente(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(RAIZ / "app_edu.py", default_timeout=20).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.radio), 0)
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(app.button[0].label, "Consultar / atualizar API")

    def test_resultado_exibe_cards_relogios_grafico_e_memorias(self) -> None:
        from streamlit.testing.v1 import AppTest

        parte1 = app_edu.calcular_parte1(ler_csv_parte1(ARQUIVO_PARTE1))
        parte2 = app_edu.calcular_parte2(fixture_parte2_no_formato_atual_da_api())
        app = AppTest.from_file(RAIZ / "app_edu.py", default_timeout=30).run()
        app.session_state["app_edu_resultado"] = {
            "chave": (
                2026,
                4,
                app_edu.CONSULTA_RECEITAS,
                app_edu.CONSULTA_DESPESAS,
                app_edu.VERSAO_CALCULO,
            ),
            "parte1": parte1,
            "parte2": parte2,
            "carregado_em": datetime.now().astimezone(),
        }

        app.run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.metric[0].value, "23,35%")
        self.assertEqual(len(app.get("plotly_chart")), 2)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)
        self.assertGreaterEqual(len(app.dataframe), 10)
        self.assertEqual(app.checkbox[0].label, "Ativar monitor anual")
        self.assertEqual(len(app.radio), 0)

        metricas_sem_projecao = len(app.metric)
        app.checkbox[0].check().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.radio), 1)
        self.assertEqual(len(app.metric), metricas_sem_projecao + 4)
        self.assertEqual(len(app.multiselect), 0)
        self.assertEqual(
            app.checkbox[1].label,
            "Simular reajuste sobre a MDE com impostos (exceto FUNDEB)",
        )

        app.checkbox[1].check().run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("Percentual do reajuste", [item.label for item in app.number_input])
        self.assertIn("Mês de início do reajuste", [item.label for item in app.selectbox])
        self.assertNotIn(
            "Base agregada de pessoal elegível afetada em 2026",
            [item.label for item in app.number_input],
        )


if __name__ == "__main__":
    unittest.main()
