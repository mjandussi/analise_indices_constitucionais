"""Testes da fronteira de extração da aplicação de educação."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app_educacao.extracao import (
    CONSULTA_DESPESAS,
    CONSULTA_RECEITAS,
    extrair_dados_educacao,
    ler_credenciais,
    localizar_snapshot,
    main,
    persistir_dados_educacao,
)


class _SiafeAPIFalsa:
    inicializacoes: list[tuple[str, str]] = []
    entradas = 0
    saidas = 0

    def __init__(self, *, usuario: str, senha: str) -> None:
        self.inicializacoes.append((usuario, senha))

    def __enter__(self) -> "_SiafeAPIFalsa":
        type(self).entradas += 1
        return self

    def __exit__(self, *_: object) -> None:
        type(self).saidas += 1


class TestExtracaoEmMemoria(unittest.TestCase):
    def setUp(self) -> None:
        _SiafeAPIFalsa.inicializacoes.clear()
        _SiafeAPIFalsa.entradas = 0
        _SiafeAPIFalsa.saidas = 0

    def test_consulta_as_duas_partes_na_mesma_sessao_sem_persistir(self) -> None:
        esperado = {"parte1": [{"descricao": "Receita"}], "parte2": []}

        with (
            patch(
                "app_educacao.extracao.consultar_dados_educacao",
                return_value=esperado,
            ) as consultar,
            tempfile.TemporaryDirectory() as temporaria,
            patch("app_educacao.extracao.PASTA_DADOS_EXTRAIDOS", Path(temporaria) / "dados"),
        ):
            recebido = extrair_dados_educacao(
                2026,
                4,
                timeout=45,
                fabrica_api=_SiafeAPIFalsa,
                credenciais=("usuario-teste", "senha-teste"),
            )

            self.assertEqual(recebido, esperado)
            self.assertFalse((Path(temporaria) / "dados").exists())

        self.assertEqual(
            _SiafeAPIFalsa.inicializacoes,
            [("usuario-teste", "senha-teste")],
        )
        self.assertEqual(_SiafeAPIFalsa.entradas, 1)
        self.assertEqual(_SiafeAPIFalsa.saidas, 1)
        consultar.assert_called_once_with(
            unittest.mock.ANY,
            exercicio=2026,
            periodo=4,
            consulta_parte1=CONSULTA_RECEITAS,
            consulta_parte2=CONSULTA_DESPESAS,
            timeout=45,
            tentativas_por_consulta=3,
            espera_inicial=1.0,
        )

    def test_ambiente_tem_precedencia_sobre_arquivo_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            arquivo_env = Path(temporaria) / ".env"
            arquivo_env.write_text(
                "SIAFE_USUARIO=usuario-arquivo\nSIAFE_SENHA=senha-arquivo\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"SIAFE_USUARIO": "usuario-ambiente", "SIAFE_SENHA": "senha-ambiente"},
                clear=True,
            ):
                self.assertEqual(
                    ler_credenciais(arquivo_env),
                    ("usuario-ambiente", "senha-ambiente"),
                )


class TestPersistenciaExplicita(unittest.TestCase):
    def test_publica_json_csv_e_metadados_sem_converter_decimal_em_float(self) -> None:
        dados = {
            "parte1": [
                {
                    "Descrição": "Receita própria",
                    "Receita Arrecadada": Decimal("25852525422.83"),
                }
            ],
            "parte2": {
                "dados": [
                    {
                        "Descrição": "(+) Aplicação",
                        "Despesa Liquidada": "6037355107.77",
                    }
                ]
            },
        }

        with tempfile.TemporaryDirectory() as temporaria:
            raiz = Path(temporaria)
            snapshot = persistir_dados_educacao(
                dados,
                2026,
                4,
                pasta_saida=raiz,
            )

            self.assertEqual(snapshot.parent, raiz.resolve() / "2026" / "04")
            self.assertEqual(
                {arquivo.name for arquivo in snapshot.iterdir()},
                {"parte1.json", "parte1.csv", "parte2.json", "parte2.csv", "metadados.json"},
            )
            self.assertFalse(
                any(item.name.startswith(".extracao_") for item in snapshot.parent.iterdir())
            )

            parte1_json = json.loads((snapshot / "parte1.json").read_text(encoding="utf-8"))
            self.assertEqual(
                parte1_json[0]["Receita Arrecadada"],
                "25852525422.83",
            )
            with (snapshot / "parte1.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as arquivo:
                parte1_csv = list(csv.DictReader(arquivo, delimiter=";"))
            self.assertEqual(
                parte1_csv[0]["Receita Arrecadada"],
                "25852525422.83",
            )

            metadados = json.loads(
                (snapshot / "metadados.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadados["consultas"]["parte1"], "084835")
            self.assertEqual(metadados["consultas"]["parte2"], "084837")
            self.assertEqual(
                metadados["quantidade_registros"], {"parte1": 1, "parte2": 1}
            )
            self.assertNotIn("usuario", json.dumps(metadados).lower())
            self.assertNotIn("senha", json.dumps(metadados).lower())

            self.assertEqual(localizar_snapshot(2026, 4, pasta_saida=raiz), snapshot)

    def test_falha_de_serializacao_nao_publica_snapshot_parcial(self) -> None:
        dados = {
            "parte1": [{"valor": object()}],
            "parte2": [{"valor": "ok"}],
        }

        with tempfile.TemporaryDirectory() as temporaria:
            raiz = Path(temporaria)
            with self.assertRaisesRegex(TypeError, "não é serializável"):
                persistir_dados_educacao(dados, 2026, 4, pasta_saida=raiz)
            pasta_periodo = raiz / "2026" / "04"
            self.assertEqual(list(pasta_periodo.iterdir()), [])

    def test_localizador_ignora_pasta_incompleta_mais_nova(self) -> None:
        dados = {"parte1": [{"valor": "1"}], "parte2": [{"valor": "2"}]}
        with tempfile.TemporaryDirectory() as temporaria:
            raiz = Path(temporaria)
            valido = persistir_dados_educacao(dados, 2026, 4, pasta_saida=raiz)
            incompleto = valido.parent / "extracao_99999999T999999_999999Z_incompleto"
            incompleto.mkdir()
            (incompleto / "parte1.csv").write_text("valor\n1\n", encoding="utf-8")

            self.assertEqual(localizar_snapshot(2026, 4, pasta_saida=raiz), valido)

    def test_cli_publica_csv_e_imprime_pasta(self) -> None:
        dados = {"parte1": [], "parte2": []}
        pasta = Path("C:/dados/snapshot")
        saida = io.StringIO()
        with patch(
            "app_educacao.extracao.extrair_e_persistir_dados_educacao",
            return_value=(dados, pasta),
        ) as extrair, patch("sys.stdout", saida):
            codigo = main(["2026", "4", "--pasta-saida", "saida", "--timeout", "45"])

        self.assertEqual(codigo, 0)
        self.assertEqual(saida.getvalue().strip(), str(pasta))
        extrair.assert_called_once_with(2026, 4, pasta_saida=Path("saida"), timeout=45)


if __name__ == "__main__":
    unittest.main()
