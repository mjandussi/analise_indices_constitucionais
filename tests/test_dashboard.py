"""Testes offline da camada de apresentação do dashboard."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from indices_constitucionais.dashboard import (
    carregar_resultado_referencia,
    mensagem_erro_segura,
    montar_linhas_estagios,
    montar_view_model,
)
from indices_constitucionais import ErroRegraNegocio, calcular_parte1


class TestViewModelDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resultado = carregar_resultado_referencia()

    def test_monta_cards_liquidados_sem_recalcular_em_float(self) -> None:
        view_model = montar_view_model(self.resultado, "despesa_liquidada")

        self.assertEqual(view_model["cards"][0]["valor"], "23,35%")
        self.assertEqual(view_model["cards"][0]["delta"], "-1,65 p.p. ante 25%")
        self.assertEqual(
            view_model["metricas"]["indice_aplicacao_percentual"].quantize(
                Decimal("0.0001")
            ),
            Decimal("23.3531"),
        )
        self.assertEqual(
            view_model["metricas"]["deficit_para_minimo"],
            Decimal("425776247.94"),
        )
        self.assertEqual(view_model["situacao"]["tipo"], "error")
        self.assertEqual(
            view_model["cards"][3]["rotulo"], "Falta para o mínimo do período"
        )

    def test_visao_anual_permanece_fixa_na_despesa_liquidada(self) -> None:
        view_model = montar_view_model(self.resultado, "despesa_paga")

        self.assertEqual(view_model["estagio"], "despesa_paga")
        visao_anual = view_model["visao_anual"]
        self.assertEqual(visao_anual["estagio"], "despesa_liquidada")
        metricas_anuais = visao_anual["metricas"]
        self.assertEqual(
            metricas_anuais["aplicacao_educacao"], Decimal("6037355107.77")
        )
        self.assertEqual(
            metricas_anuais["minimo_constitucional_previsto"],
            Decimal("17238721284.92"),
        )
        self.assertEqual(
            metricas_anuais["indice_sobre_receita_prevista_percentual"].quantize(
                Decimal("0.0001")
            ),
            Decimal("8.7555"),
        )
        self.assertEqual(
            metricas_anuais[
                "atingimento_do_minimo_previsto_percentual"
            ].quantize(Decimal("0.0001")),
            Decimal("35.0221"),
        )
        self.assertEqual(
            metricas_anuais["deficit_para_minimo_previsto"],
            Decimal("11201366177.15"),
        )

    def test_preserva_ordem_e_situacao_dos_cinco_estagios(self) -> None:
        linhas = montar_linhas_estagios(self.resultado)

        self.assertEqual(
            tuple(linha["estagio"] for linha in linhas),
            (
                "dotacao_atual",
                "despesa_autorizada",
                "despesa_empenhada",
                "despesa_liquidada",
                "despesa_paga",
            ),
        )
        self.assertEqual(
            tuple(linha["atingiu_minimo"] for linha in linhas),
            (True, True, False, False, False),
        )
        esperados = ("41.2061", "37.6586", "24.2790", "23.3531", "22.8821")
        self.assertEqual(
            tuple(
                str(linha["indice_percentual"].quantize(Decimal("0.0001")))
                for linha in linhas
            ),
            esperados,
        )

    def test_redutores_e_tabelas_sao_formatados_para_a_interface(self) -> None:
        view_model = montar_view_model(self.resultado, "despesa_liquidada")

        self.assertEqual(len(view_model["linhas_redutores"]), 5)
        self.assertEqual(len(view_model["quadro_resumo"]), 7)
        self.assertEqual(len(view_model["relatorio_calculado"]), 27)
        self.assertEqual(
            view_model["relatorio_calculado"][-1]["Despesa liquidada"],
            "R$ 6.037.355.107,77",
        )
        self.assertEqual(
            view_model["linhas_redutores"][1]["valor"], Decimal("58377935.29")
        )
        self.assertEqual(
            view_model["linhas_redutores"][1]["valor_formatado"],
            "R$ 58.377.935,29",
        )
        self.assertEqual(len(view_model["detalhes_a"]), 2)
        self.assertEqual(len(view_model["detalhes_c"]), 9)

    def test_indice_indisponivel_nao_e_rotulado_como_excedente(self) -> None:
        parte1 = replace(
            self.resultado.parte1,
            base_arrecadada=Decimal("0"),
            minimo_sobre_arrecadada=Decimal("0"),
        )
        total = dict(self.resultado.parte2.total_aplicado)
        total["despesa_liquidada"] = Decimal("100")
        parte2 = replace(self.resultado.parte2, total_aplicado=total)
        resultado = replace(self.resultado, parte1=parte1, parte2=parte2)

        view_model = montar_view_model(resultado, "despesa_liquidada")

        self.assertEqual(view_model["situacao"]["titulo"], "Índice indisponível")
        self.assertEqual(
            view_model["cards"][3]["rotulo"], "Saldo do mínimo do período"
        )
        self.assertEqual(view_model["cards"][3]["valor"], "—")

    def test_igualdade_exata_e_rotulada_como_no_limite(self) -> None:
        total = dict(self.resultado.parte2.total_aplicado)
        total["despesa_liquidada"] = self.resultado.parte1.minimo_sobre_arrecadada
        parte2 = replace(self.resultado.parte2, total_aplicado=total)
        resultado = replace(self.resultado, parte2=parte2)

        view_model = montar_view_model(resultado, "despesa_liquidada")

        self.assertTrue(view_model["metricas"]["atingiu_minimo"])
        self.assertEqual(
            view_model["cards"][3]["rotulo"], "No mínimo do período — 25%"
        )
        self.assertEqual(view_model["cards"][3]["valor"], "R$ 0,00")

    def test_quase_25_por_cento_nao_e_exibido_como_25(self) -> None:
        parte1 = replace(
            self.resultado.parte1,
            base_arrecadada=Decimal("10000"),
            minimo_sobre_arrecadada=Decimal("2500"),
        )
        total = dict(self.resultado.parte2.total_aplicado)
        total["despesa_liquidada"] = Decimal("2499.90")
        resultado = replace(
            self.resultado,
            parte1=parte1,
            parte2=replace(self.resultado.parte2, total_aplicado=total),
        )

        view_model = montar_view_model(resultado, "despesa_liquidada")

        self.assertFalse(view_model["metricas"]["atingiu_minimo"])
        self.assertEqual(view_model["cards"][0]["valor"], "24,9990%")
        self.assertEqual(view_model["cards"][0]["delta"], "-0,0010 p.p. ante 25%")
        self.assertEqual(view_model["linhas_estagios"][3]["indice_formatado"], "24,9990%")

    def test_diferenca_de_um_centavo_em_base_bilionaria_nao_some_na_tela(self) -> None:
        parte1 = replace(
            self.resultado.parte1,
            base_arrecadada=Decimal("10000000000.00"),
            minimo_sobre_arrecadada=Decimal("2500000000.00"),
        )
        total = dict(self.resultado.parte2.total_aplicado)
        total["despesa_liquidada"] = Decimal("2499999999.99")
        resultado = replace(
            self.resultado,
            parte1=parte1,
            parte2=replace(self.resultado.parte2, total_aplicado=total),
        )

        view_model = montar_view_model(resultado, "despesa_liquidada")

        self.assertFalse(view_model["metricas"]["atingiu_minimo"])
        self.assertEqual(view_model["cards"][0]["valor"], "24,9999999999%")
        self.assertEqual(
            view_model["cards"][0]["delta"],
            "-0,0000000001 p.p. ante 25%",
        )

    def test_minimo_sobe_ao_centavo_para_nunca_ficar_abaixo_de_25(self) -> None:
        parte1 = calcular_parte1(
            [
                {
                    "Descrição": "(+) Receita teste",
                    "Receita Prevista": "100,01",
                    "Receita Arrecadada": "100,01",
                }
            ]
        )

        self.assertEqual(parte1.minimo_sobre_prevista, Decimal("25.01"))
        self.assertEqual(parte1.minimo_sobre_arrecadada, Decimal("25.01"))

    def test_margem_usa_arredondamento_financeiro_meio_para_cima(self) -> None:
        parte1 = replace(
            self.resultado.parte1,
            base_arrecadada=Decimal("10000"),
            minimo_sobre_arrecadada=Decimal("2500"),
        )
        total = dict(self.resultado.parte2.total_aplicado)
        total["despesa_liquidada"] = Decimal("2335.50")
        resultado = replace(
            self.resultado,
            parte1=parte1,
            parte2=replace(self.resultado.parte2, total_aplicado=total),
        )

        view_model = montar_view_model(resultado, "despesa_liquidada")

        self.assertEqual(view_model["cards"][0]["valor"], "23,36%")
        self.assertEqual(view_model["cards"][0]["delta"], "-1,65 p.p. ante 25%")

    def test_base_arrecadada_negativa_e_rejeitada(self) -> None:
        with self.assertRaisesRegex(ErroRegraNegocio, "não podem ser negativas"):
            replace(self.resultado.parte1, base_arrecadada=Decimal("-0.01"))

    def test_csv_ausente_falha_sem_escolher_arquivo_por_adivinhacao(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaisesRegex(FileNotFoundError, "exatamente um CSV"):
                carregar_resultado_referencia(Path(pasta))


class _RespostaFalsa:
    status_code = 500

    def json(self) -> dict[str, str]:
        return {"erro": "SEGREDO_QUE_NAO_PODE_APARECER"}


class _ErroHttpFalso(Exception):
    def __init__(self) -> None:
        super().__init__("mensagem que não deve prevalecer")
        self.response = _RespostaFalsa()


class _RespostaFormulaRp:
    status_code = 500

    def json(self) -> dict[str, str]:
        return {
            "erro": (
                "Não foi possível avaliar a expressão "
                "[(-) Restos a Pagar Cancelados (I) - (II)].[(I) Total MDE]"
            )
        }


class _ErroFormulaRp(Exception):
    def __init__(self) -> None:
        super().__init__("corpo integral não deve ser apresentado")
        self.response = _RespostaFormulaRp()
        self.consulta_id = "084837"
        self.tentativas = 3


class TestMensagemErroDashboard(unittest.TestCase):
    def test_resume_resposta_http_sem_url_ou_payload_integral(self) -> None:
        mensagem = mensagem_erro_segura(_ErroHttpFalso())

        self.assertIn("HTTP 500", mensagem)
        self.assertIn("falha interna", mensagem)
        self.assertNotIn("SEGREDO_QUE_NAO_PODE_APARECER", mensagem)
        self.assertNotIn("http://", mensagem)

    def test_identifica_formula_conhecida_sem_expor_corpo_integral(self) -> None:
        mensagem = mensagem_erro_segura(_ErroFormulaRp())

        self.assertIn("Consulta 084837", mensagem)
        self.assertIn("3 tentativas", mensagem)
        self.assertIn("Restos a Pagar Cancelados (I) - (II)", mensagem)
        self.assertNotIn("corpo integral", mensagem)


if __name__ == "__main__":
    unittest.main()
