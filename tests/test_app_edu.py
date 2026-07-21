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


class TestCalculosAppEdu(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dados_parte1 = ler_csv_parte1(ARQUIVO_PARTE1)
        cls.dados_parte2 = ler_csv_parte2(ARQUIVO_PARTE2)

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
        coluna_descricao = next(iter(dados[0]))
        linha = next(
            item
            for item in dados
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
            in app_edu.normalizar_texto(item[coluna_descricao])
        )
        linha[coluna_descricao] = "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO"
        for coluna in list(linha)[1:]:
            linha[coluna] = str(-app_edu.para_decimal(linha[coluna]))

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
            parte2["origem_total_fundeb"], "0 - valor do nó FUNDEB-FILTRO"
        )

    def test_configuracao_usa_somente_as_consultas_api_atuais(self) -> None:
        self.assertEqual(app_edu.CONSULTA_RECEITAS, "084835")
        self.assertEqual(app_edu.CONSULTA_DESPESAS, "084837")

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
        parte2 = app_edu.calcular_parte2(ler_csv_parte2(ARQUIVO_PARTE2))
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


if __name__ == "__main__":
    unittest.main()
