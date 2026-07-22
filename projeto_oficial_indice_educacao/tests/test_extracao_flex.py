"""Testes do extrator Flexvision de arquivo único, sem acessar a internet."""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import extracao_flex  # noqa: E402


class RespostaFalsa:
    def __init__(self, dados):
        self.conteudo = json.dumps(dados).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.conteudo


class TestExtracaoFlex(unittest.TestCase):
    def test_le_credenciais_do_env_sem_pacote_externo(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            arquivo_env = Path(temporaria) / ".env"
            arquivo_env.write_text(
                "SIAFE_USUARIO=usuario-arquivo\nSIAFE_SENHA='senha-arquivo'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                credenciais = extracao_flex.ler_credenciais(arquivo_env)

        self.assertEqual(credenciais, ("usuario-arquivo", "senha-arquivo"))

    def test_autentica_uma_vez_e_executa_varias_consultas(self) -> None:
        respostas = [
            RespostaFalsa({"token": "token-teste", "tipo": "Bearer"}),
            RespostaFalsa([{"consulta": 1}]),
            RespostaFalsa([{"consulta": 2}]),
            RespostaFalsa([{"consulta": 3}]),
        ]
        consultas = [
            {"nome": "uma", "consulta_id": "084835", "parametros": [2026, 4]},
            {"nome": "duas", "consulta_id": "084837", "parametros": [2026, 4]},
            {"nome": "tres", "consulta_id": "084999", "parametros": []},
        ]

        with (
            patch("extracao_flex.URL_API", "https://api.exemplo/siafe"),
            patch("extracao_flex.TIMEOUT", 45),
            patch("extracao_flex.urlopen", side_effect=respostas) as abrir,
        ):
            resultado = extracao_flex.consultar_varias(
                consultas,
                usuario="usuario",
                senha="senha",
            )

        self.assertEqual(set(resultado), {"uma", "duas", "tres"})
        self.assertEqual(abrir.call_count, 4)
        requisicoes = [chamada.args[0] for chamada in abrir.call_args_list]
        self.assertEqual(requisicoes[0].full_url, "https://api.exemplo/siafe/auth")
        self.assertEqual(
            json.loads(requisicoes[0].data.decode("utf-8")),
            {"usuario": "usuario", "senha": "senha"},
        )
        self.assertEqual(
            requisicoes[1].full_url,
            "https://api.exemplo/siafe/flexvision-consulta/084835?params=2026%2C4",
        )
        self.assertEqual(requisicoes[1].get_header("Authorization"), "Bearer token-teste")
        self.assertNotIn("?", requisicoes[3].full_url)

    def test_grava_um_json_e_um_csv_para_cada_consulta(self) -> None:
        consultas = [
            {"nome": "parte1", "consulta_id": "084835", "parametros": [2026, 4]},
            {"nome": "parte2", "consulta_id": "084837", "parametros": [2026, 4]},
        ]
        respostas = {
            "parte1": {"dados": [{"Descrição": "Receita", "Valor": "1.000,00"}]},
            "parte2": [{"Descrição": "Despesa", "Valor": 500}],
        }

        with tempfile.TemporaryDirectory() as temporaria, patch(
            "extracao_flex.consultar_varias", return_value=respostas
        ):
            arquivos = extracao_flex.extrair_consultas(
                consultas,
                pasta_saida=temporaria,
                usuario="usuario",
                senha="senha",
            )

            self.assertEqual(set(arquivos), {"parte1", "parte2"})
            self.assertTrue((Path(temporaria) / "parte1.json").is_file())
            self.assertTrue((Path(temporaria) / "parte2.json").is_file())
            with arquivos["parte1"].open(
                "r", encoding="utf-8-sig", newline=""
            ) as arquivo:
                linhas = list(csv.DictReader(arquivo, delimiter=";"))

        self.assertEqual(linhas, [{"Descrição": "Receita", "Valor": "1.000,00"}])


if __name__ == "__main__":
    unittest.main()
