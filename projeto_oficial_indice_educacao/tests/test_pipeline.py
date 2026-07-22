"""Testes rápidos do projeto portátil, sem acesso à API."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dados import calcular_metricas, processar_csvs  # noqa: E402
from extracao import (  # noqa: E402
    extrair_dados_educacao,
    localizar_dados_educacao,
)
from extracao_flex import gravar_resultados  # noqa: E402
from regras.projecao import calcular_monitor_meta  # noqa: E402


ESTAGIOS = (
    "Dotação Atual",
    "Despesa Autorizada",
    "Despesa Empenhada",
    "Despesa Liquidada",
    "Despesa Paga",
)


def linha_parte2(descricao: str, valor: int) -> dict[str, object]:
    return {"Descrição": descricao, **{estagio: valor for estagio in ESTAGIOS}}


def payload_sintetico() -> dict[str, list[dict[str, object]]]:
    """Cobre FUNDEB e os insumos obrigatórios dos redutores A–D."""

    parte1 = [
        {
            "Descrição": "(+) Impostos",
            "Receita Prevista": "1.000,00",
            "Receita Arrecadada": "800,00",
        },
        {
            "Descrição": "(-) Transferências aos Municípios",
            "Receita Prevista": "-200,00",
            "Receita Arrecadada": "-100,00",
        },
        {
            "Descrição": "5- TOTAL DESTINADO AO FUNDEB",
            "Receita Prevista": "200,00",
            "Receita Arrecadada": "50,00",
        },
        {
            "Descrição": "TOTAL - BASE DE CÁLCULO",
            "Receita Prevista": "800,00",
            "Receita Arrecadada": "700,00",
        },
    ]
    parte2 = [
        linha_parte2("(+) Fonte 100", 1000),
        linha_parte2("(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO", -50),
        linha_parte2(
            "A - SUPERAVIT FINANCEIRO DOS RECURSOS TRANSFERIDOS DO FUNDEB-"
            "IMPOSTOS E TRANSF DE IMPOSTOS",
            100,
        ),
        linha_parte2(
            "A - APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO ANTERIOR-"
            "IMPOSTOS E TRANSF DE IMPOSTOS",
            100,
        ),
        linha_parte2(
            "A - SUPERAVIT FINANCEIRO DOS RECURSOS TRANSFERIDOS DO FUNDEB-"
            "COMPLEMENTAÇÃO DA UNIÃO",
            50,
        ),
        linha_parte2(
            "A - APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO ANTERIOR-"
            "COMPLEMENTAÇÃO DA UNIÃO",
            50,
        ),
        linha_parte2("B - RECEITAS RECEBIDAS DO FUNDEB", 200),
        linha_parte2(
            "B - TOTAL DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB "
            "RECEBIDAS NO EXERCÍCIO",
            200,
        ),
        linha_parte2(
            "D - Restos a Pagar Cancelados (RPP e RPNP) Inscritos em 2025",
            10,
        ),
        linha_parte2("D - EXCESSO APLICADO EM EDUCAÇÃO - Inscritos em 2025", 10),
        linha_parte2("C - RP Cancelado TAC - Inscritos em 2016", 0),
        linha_parte2("(-) Outra despesa não computável", 50),
    ]
    return {"parte1": parte1, "parte2": parte2}


class TestFluxoCsv(unittest.TestCase):
    def test_json_gera_csv_e_etl_le_somente_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            raiz_dados = Path(temporaria)
            pasta = raiz_dados.resolve() / "2026" / "04"
            gravar_resultados(payload_sintetico(), pasta)

            self.assertEqual(pasta, raiz_dados.resolve() / "2026" / "04")
            self.assertTrue((pasta / "parte1.csv").is_file())
            self.assertTrue((pasta / "parte2.csv").is_file())
            self.assertTrue((pasta / "parte1.json").is_file())
            self.assertTrue((pasta / "parte2.json").is_file())

            # JSON é a evidência original; a ETL deve continuar lendo os CSVs.
            (pasta / "parte1.json").write_text("inválido", encoding="utf-8")
            (pasta / "parte2.json").write_text("inválido", encoding="utf-8")
            resultado = processar_csvs(pasta)
            metricas = calcular_metricas(
                resultado["parte1"], resultado["parte2"], "despesa_liquidada"
            )

            self.assertEqual(resultado["parte1"]["base_arrecadada"], Decimal("700.00"))
            self.assertEqual(resultado["parte2"]["total_fundeb"]["valores"]["despesa_liquidada"], Decimal("50.00"))
            self.assertEqual(metricas["aplicado"], Decimal("1000.00"))
            self.assertEqual(metricas["base_prevista"], Decimal("800.00"))
            self.assertEqual(metricas["liquidado"], Decimal("1000.00"))
            self.assertEqual(metricas["indice_anual"], Decimal("125.00"))
            self.assertEqual(metricas["execucao_meta_anual"], Decimal("500.00"))
            self.assertEqual(
                localizar_dados_educacao(2026, 4, pasta_saida=raiz_dados),
                pasta,
            )

    def test_projecao_preserva_decimais(self) -> None:
        parte1 = {
            "base_arrecadada": Decimal("400.00"),
            "fundeb_realizado": Decimal("80.00"),
            "fundeb_previsto": Decimal("240.00"),
        }
        parte2 = {
            "total_aplicado": {"despesa_liquidada": Decimal("100.00")},
            "valores_positivos": {"despesa_liquidada": Decimal("130.00")},
            "total_fundeb": {"valores": {"despesa_liquidada": Decimal("80.00")}},
            "outras_deducoes": {"despesa_liquidada": Decimal("10.00")},
            "redutor_a": {"despesa_liquidada": Decimal("5.00")},
            "redutor_b": {"despesa_liquidada": Decimal("15.00")},
            "redutor_c": {"despesa_liquidada": Decimal("0.00")},
            "redutor_d": {"despesa_liquidada": Decimal("0.00")},
        }

        monitor = calcular_monitor_meta(
            parte1,
            parte2,
            4,
            base_anual_estimada=Decimal("1000.00"),
            meta_percentual=Decimal("25"),
            percentual_reajuste=Decimal("10"),
            mes_inicio_reajuste=7,
        )
        self.assertEqual(monitor["aplicacao_projetada"], Decimal("346.00"))
        self.assertEqual(monitor["indice_projetado"], Decimal("34.60"))


class TestExtracaoApi(unittest.TestCase):
    def test_monta_as_duas_consultas_para_o_extrator_local(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria, patch(
            "extracao.extrair_consultas"
        ) as extrair:
            pasta = extrair_dados_educacao(
                2026,
                4,
                temporaria,
                credenciais=("usuario", "senha"),
            )

        pasta_esperada = Path(temporaria).resolve() / "2026" / "04"
        self.assertEqual(pasta, pasta_esperada)
        extrair.assert_called_once_with(
            [
                {
                    "nome": "parte1",
                    "consulta_id": "084835",
                    "parametros": [2026, 4],
                },
                {
                    "nome": "parte2",
                    "consulta_id": "084837",
                    "parametros": [2026, 4],
                },
            ],
            pasta_esperada,
            "usuario",
            "senha",
            RAIZ / ".env",
        )


class TestIndependencia(unittest.TestCase):
    def test_copia_nao_importa_o_repositorio_original(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            copia = Path(temporaria) / "projeto"
            shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns("__pycache__"))
            programa = textwrap.dedent(
                f"""
                import importlib.abc
                import pathlib
                import sys

                raiz = pathlib.Path({str(copia)!r}).resolve()
                sys.path.insert(0, str(raiz))

                class BloquearAntigos(importlib.abc.MetaPathFinder):
                    def find_spec(self, fullname, path=None, target=None):
                        if fullname.split('.')[0] in {{'indices_constitucionais', 'app_educacao', 'app_edu'}}:
                            raise ImportError('dependência antiga: ' + fullname)
                        return None

                sys.meta_path.insert(0, BloquearAntigos())
                import config, dados, extracao, extracao_flex, regras
                for modulo in (config, dados, extracao, extracao_flex, regras):
                    assert pathlib.Path(modulo.__file__).resolve().is_relative_to(raiz)
                """
            )
            subprocess.run(
                [sys.executable, "-I", "-c", programa],
                cwd=copia,
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
