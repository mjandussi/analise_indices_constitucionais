"""Smoke tests dos dois dashboards executáveis separadamente."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


STREAMLIT_DISPONIVEL = importlib.util.find_spec("streamlit") is not None
RAIZ = Path(__file__).resolve().parents[1]


@unittest.skipUnless(STREAMLIT_DISPONIVEL, "Streamlit não instalado.")
class TestDashboardsSeparados(unittest.TestCase):
    def test_dashboard_indice_abre_diretamente(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            RAIZ / "app_educacao" / "dash_indice.py",
            default_timeout=20,
        ).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.button[0].label, "Consultar / atualizar API")

    def test_dashboard_projecao_abre_diretamente(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            RAIZ / "app_educacao" / "dash_projecao.py",
            default_timeout=20,
        ).run()
        self.assertEqual(list(app.exception), [])


if __name__ == "__main__":
    unittest.main()
