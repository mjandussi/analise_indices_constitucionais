"""Testes do isolamento e das retentativas das consultas Flexvision."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from indices_constitucionais import ErroConsultaFlexvision
from indices_constitucionais.dashboard import mensagem_erro_segura
from indices_constitucionais.flexvision import (
    CONSULTA_PARTE1,
    CONSULTA_PARTE2,
    consultar_dados_educacao,
)


class _RespostaHttp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _ErroHttp(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code} com conteúdo que não deve ser exibido")
        self.response = _RespostaHttp(status_code)


class _FlexvisionFalso:
    def __init__(self, respostas: dict[str, list[object]]) -> None:
        self.respostas = {chave: list(valores) for chave, valores in respostas.items()}
        self.chamadas: list[str] = []

    def consultar(self, consulta_id: str, **_: object) -> object:
        self.chamadas.append(consulta_id)
        resposta = self.respostas[consulta_id].pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class _ApiFalsa:
    def __init__(self, respostas: dict[str, list[object]]) -> None:
        self.flexvision = _FlexvisionFalso(respostas)


class TestConsultasFlexvision(unittest.TestCase):
    @patch("indices_constitucionais.flexvision.time.sleep")
    def test_repete_http_500_e_preserva_o_id_da_consulta(self, dormir) -> None:
        api = _ApiFalsa(
            {
                CONSULTA_PARTE1: [[{"parte": 1}]],
                CONSULTA_PARTE2: [_ErroHttp(500), _ErroHttp(500), [{"parte": 2}]],
            }
        )

        resultado = consultar_dados_educacao(api, 2026, 4)

        self.assertEqual(resultado["parte1"], [{"parte": 1}])
        self.assertEqual(resultado["parte2"], [{"parte": 2}])
        self.assertEqual(
            api.flexvision.chamadas,
            [
                CONSULTA_PARTE1,
                CONSULTA_PARTE2,
                CONSULTA_PARTE2,
                CONSULTA_PARTE2,
            ],
        )
        self.assertEqual(
            [chamada.args[0] for chamada in dormir.call_args_list],
            [1.0, 2.0],
        )

    @patch("indices_constitucionais.flexvision.time.sleep")
    def test_falha_final_informa_consulta_status_e_tentativas(self, dormir) -> None:
        api = _ApiFalsa(
            {
                CONSULTA_PARTE1: [[{"parte": 1}]],
                CONSULTA_PARTE2: [_ErroHttp(500), _ErroHttp(500), _ErroHttp(500)],
            }
        )

        with self.assertRaises(ErroConsultaFlexvision) as contexto:
            consultar_dados_educacao(api, 2026, 4)

        erro = contexto.exception
        self.assertEqual(erro.consulta_id, CONSULTA_PARTE2)
        self.assertEqual(erro.tentativas, 3)
        mensagem = mensagem_erro_segura(erro)
        self.assertIn(f"Consulta {CONSULTA_PARTE2}", mensagem)
        self.assertIn("HTTP 500", mensagem)
        self.assertIn("3 tentativas", mensagem)
        self.assertNotIn("conteúdo que não deve ser exibido", mensagem)
        self.assertEqual(dormir.call_count, 2)

    @patch("indices_constitucionais.flexvision.time.sleep")
    def test_http_nao_transitorio_nao_e_repetido(self, dormir) -> None:
        api = _ApiFalsa(
            {
                CONSULTA_PARTE1: [_ErroHttp(403)],
                CONSULTA_PARTE2: [[{"parte": 2}]],
            }
        )

        with self.assertRaises(ErroConsultaFlexvision) as contexto:
            consultar_dados_educacao(api, 2026, 4)

        self.assertEqual(contexto.exception.consulta_id, CONSULTA_PARTE1)
        self.assertEqual(contexto.exception.tentativas, 1)
        dormir.assert_not_called()

    def test_valida_configuracao_de_retentativa(self) -> None:
        api = _ApiFalsa({CONSULTA_PARTE1: [], CONSULTA_PARTE2: []})

        with self.assertRaisesRegex(ValueError, "maior ou igual a 1"):
            consultar_dados_educacao(api, 2026, 4, tentativas_por_consulta=0)
        with self.assertRaisesRegex(ValueError, "não pode ser negativa"):
            consultar_dados_educacao(api, 2026, 4, espera_inicial=-1)


if __name__ == "__main__":
    unittest.main()
