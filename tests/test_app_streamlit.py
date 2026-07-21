"""Smoke test headless da página; ignorado quando Streamlit não está instalado."""

from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


STREAMLIT_DISPONIVEL = importlib.util.find_spec("streamlit") is not None


@unittest.skipUnless(STREAMLIT_DISPONIVEL, "Streamlit não instalado neste ambiente.")
class TestAppStreamlit(unittest.TestCase):
    def test_modo_csv_abre_e_altera_estagio_sem_excecao(self) -> None:
        from streamlit.testing.v1 import AppTest

        raiz = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()

        self.assertEqual(list(app.exception), [])
        self.assertGreaterEqual(len(app.metric), 7)
        self.assertEqual(app.metric[0].value, "23,35%")
        self.assertEqual(app.radio[0].value, "CSV de referência")
        self.assertEqual(len(app.get("plotly_chart")), 2)
        relogio_periodo = json.loads(app.get("plotly_chart")[0].proto.spec)
        relogio_anual = json.loads(app.get("plotly_chart")[1].proto.spec)
        self.assertAlmostEqual(relogio_periodo["data"][0]["value"], 23.3530574249)
        self.assertAlmostEqual(relogio_anual["data"][0]["value"], 8.7555147043)
        self.assertEqual(
            relogio_periodo["data"][0]["gauge"]["threshold"]["value"], 25.0
        )
        self.assertEqual(
            relogio_anual["data"][0]["gauge"]["threshold"]["value"], 25.0
        )
        self.assertEqual(app.metric[4].value, "R$ 68,95 bi")
        self.assertEqual(app.metric[5].value, "R$ 17,24 bi")
        self.assertEqual(app.metric[7].value, "35,02%")
        self.assertEqual(app.metric[8].value, "R$ 11,20 bi")
        self.assertTrue(
            any("35,02%" in legenda.value for legenda in app.caption),
            "A execução da meta anual deve aparecer fora do relógio.",
        )
        self.assertTrue(
            any("8,76%" in legenda.value for legenda in app.caption),
            "O índice sobre a receita prevista deve aparecer fora do relógio.",
        )

        especificacao = json.loads(app.get("vega_lite_chart")[0].proto.spec)
        self.assertEqual(
            especificacao["layer"][0]["encoding"]["x"]["sort"],
            ["Despesa empenhada", "Despesa liquidada", "Despesa paga"],
        )

        app.selectbox[1].select("Despesa paga").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.metric[0].value, "22,88%")

    def test_modo_api_nao_consulta_no_import_nem_exige_credencial_antes_do_botao(self) -> None:
        from streamlit.testing.v1 import AppTest

        raiz = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()
        app.radio[0].set_value("API Flexvision").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(app.button[0].label, "Consultar / atualizar API")

    def test_api_csv_api_descarta_snapshot_e_exige_nova_consulta(self) -> None:
        from streamlit.testing.v1 import AppTest

        from indices_constitucionais.dashboard import carregar_resultado_referencia

        raiz = Path(__file__).resolve().parents[1]
        resultado = carregar_resultado_referencia()
        with (
            patch(
                "indices_constitucionais.dashboard.carregar_resultado_api",
                return_value=resultado,
            ) as carregar,
            patch(
                "indices_constitucionais.dashboard.escopo_credenciais_api",
                return_value="escopo-teste",
            ),
        ):
            app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()
            app.radio[0].set_value("API Flexvision").run()
            app.button[0].click().run()

            self.assertEqual(list(app.exception), [])
            self.assertGreaterEqual(len(app.metric), 7)
            self.assertEqual(carregar.call_count, 1)

            app.radio[0].set_value("CSV de referência").run()
            app.radio[0].set_value("API Flexvision").run()

            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.metric), 0)
            self.assertEqual(carregar.call_count, 1)

    def test_snapshot_expirado_e_removido_no_proximo_rerun(self) -> None:
        from streamlit.testing.v1 import AppTest

        from indices_constitucionais.dashboard import carregar_resultado_referencia

        raiz = Path(__file__).resolve().parents[1]
        resultado = carregar_resultado_referencia()
        with (
            patch(
                "indices_constitucionais.dashboard.carregar_resultado_api",
                return_value=resultado,
            ),
            patch(
                "indices_constitucionais.dashboard.escopo_credenciais_api",
                return_value="escopo-teste",
            ),
        ):
            app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()
            app.radio[0].set_value("API Flexvision").run()
            app.button[0].click().run()

            snapshot = dict(app.session_state["snapshot_api_educacao"])
            snapshot["carregado_em"] = datetime.now().astimezone() - timedelta(
                minutes=16
            )
            app.session_state["snapshot_api_educacao"] = snapshot
            app.selectbox[1].select("Despesa paga").run()

            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.metric), 0)
            self.assertEqual(len(app.info), 1)
            self.assertIn("expirou", app.info[0].value)

    def test_rotacao_de_credencial_invalida_snapshot(self) -> None:
        from streamlit.testing.v1 import AppTest

        from indices_constitucionais.dashboard import carregar_resultado_referencia

        raiz = Path(__file__).resolve().parents[1]
        resultado = carregar_resultado_referencia()
        with (
            patch(
                "indices_constitucionais.dashboard.carregar_resultado_api",
                return_value=resultado,
            ),
            patch(
                "indices_constitucionais.dashboard.escopo_credenciais_api",
                return_value="credencial-anterior",
            ) as escopo,
        ):
            app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()
            app.radio[0].set_value("API Flexvision").run()
            app.button[0].click().run()

            escopo.return_value = "credencial-nova"
            app.selectbox[1].select("Despesa paga").run()

            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.metric), 0)
            self.assertEqual(len(app.info), 1)
            self.assertIn("credenciais foram alteradas", app.info[0].value)

    def test_falha_na_atualizacao_remove_resultado_anterior(self) -> None:
        from streamlit.testing.v1 import AppTest

        from indices_constitucionais.dashboard import carregar_resultado_referencia

        raiz = Path(__file__).resolve().parents[1]
        resultado = carregar_resultado_referencia()
        with (
            patch(
                "indices_constitucionais.dashboard.carregar_resultado_api",
                return_value=resultado,
            ) as carregar,
            patch(
                "indices_constitucionais.dashboard.escopo_credenciais_api",
                return_value="escopo-teste",
            ),
        ):
            app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()
            app.radio[0].set_value("API Flexvision").run()
            app.button[0].click().run()
            self.assertGreaterEqual(len(app.metric), 7)

            carregar.side_effect = RuntimeError("payload-secreto")
            app.button[0].click().run()

            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.metric), 0)
            self.assertEqual(len(app.error), 1)
            textos = " ".join(elemento.value for elemento in app.markdown)
            self.assertNotIn("payload-secreto", textos)

    def test_snapshot_com_resultado_corrompido_e_descartado(self) -> None:
        from streamlit.testing.v1 import AppTest

        raiz = Path(__file__).resolve().parents[1]
        with patch(
            "indices_constitucionais.dashboard.escopo_credenciais_api",
            return_value="escopo-teste",
        ):
            app = AppTest.from_file(raiz / "app.py", default_timeout=15).run()
            app.radio[0].set_value("API Flexvision").run()
            app.session_state["snapshot_api_educacao"] = {
                "resultado": "CORROMPIDO",
                "parametros": (2026, 4),
                "consultas": ("084835", "084837"),
                "versao_contrato": (
                    "educacao-v8-084835-084837-brutos-abcd-fundeb-filtro"
                ),
                "escopo_credencial": "escopo-teste",
                "carregado_em": datetime.now().astimezone(),
            }

            app.selectbox[1].select("Despesa paga").run()

            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.metric), 0)


if __name__ == "__main__":
    unittest.main()
