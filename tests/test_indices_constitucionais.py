"""Testes de regressão offline para os cálculos do índice de educação."""

from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from indices_constitucionais import (
    ESTAGIOS_DESPESA,
    ErroRegraNegocio,
    ErroSchemaFlexvision,
    calcular_indice_educacao,
    calcular_parte1,
    calcular_parte2,
    numero_decimal,
)
from indices_constitucionais.fontes import ler_csv_parte1, ler_csv_parte2
from indices_constitucionais.normalizacao import normalizar_texto


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_CONSULTAS = RAIZ_PROJETO / "consultas_base"


def _arquivo_unico(padrao: str) -> Path:
    """Localiza uma fixture versionada sem depender do diretório de execução."""

    encontrados = sorted(PASTA_CONSULTAS.glob(padrao))
    if len(encontrados) != 1:
        raise AssertionError(
            f"Esperado um arquivo para {padrao!r}; encontrados: "
            f"{[arquivo.name for arquivo in encontrados]!r}."
        )
    return encontrados[0]


ARQUIVO_PARTE1 = _arquivo_unico("*Parte 1_3 (2026)_*.csv")
ARQUIVO_PARTE2_BRUTO = _arquivo_unico(
    "*Parte 2_3 (2026) com FR 108 Adaptado_*.csv"
)
ARQUIVO_PARTE2_CONSOLIDADO = _arquivo_unico(
    "*Parte 2_3 (2026) com FR 108_*.csv"
)
ARQUIVO_PARTE2_ORIGINAL = _arquivo_unico(
    "*Parte 2_3 (Abr.2026)_ORIGINAL.csv"
)


COLUNAS_PARTE2 = {
    "dotacao_atual": "Dotação Atual",
    "despesa_autorizada": "Despesa Autorizada",
    "despesa_empenhada": "Despesa Empenhada",
    "despesa_liquidada": "Despesa Liquidada",
    "despesa_paga": "Despesa Paga",
}


def _linha_parte2(descricao: str, *valores: int | str | Decimal) -> dict[str, object]:
    if len(valores) != len(ESTAGIOS_DESPESA):
        raise AssertionError("A fixture deve informar os cinco estágios da despesa.")
    registro: dict[str, object] = {"Descrição": descricao}
    for estagio, valor in zip(ESTAGIOS_DESPESA, valores):
        registro[COLUNAS_PARTE2[estagio]] = valor
    return registro


def _fixture_parte2_bruta() -> list[dict[str, object]]:
    """Resposta sintética no formato da consulta bruta 084837.

    As letras C/D reproduzem a inversão existente na consulta: as linhas de
    TAC chegam com C, enquanto restos a pagar e excesso de MDE chegam com D.
    """

    return [
        _linha_parte2("(+) Fonte 100", 1000, 1100, 1200, 1300, 1400),
        _linha_parte2(
            "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB", 0, 0, 0, 0, 0
        ),
        _linha_parte2(
            "A - 7.9.9.1.1.44.01 - SUPERAVIT FINANCEIRO DOS RECURSOS "
            "TRANSFERIDOS DO FUNDEB-IMPOSTOS E TRANSF DE IMPOSTOS",
            100,
            110,
            120,
            130,
            140,
        ),
        _linha_parte2(
            "A - APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO "
            "ANTERIOR-IMPOSTOS E TRANSF DE IMPOSTOS",
            40,
            120,
            20,
            200,
            50,
        ),
        _linha_parte2(
            "A - 7.9.9.1.1.44.01 - SUPERAVIT FINANCEIRO DOS RECURSOS "
            "TRANSFERIDOS DO FUNDEB-COMPLEMENTAÇÃO DA UNIÃO",
            50,
            60,
            70,
            80,
            90,
        ),
        _linha_parte2(
            "A - APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO "
            "ANTERIOR-COMPLEMENTAÇÃO DA UNIÃO",
            10,
            20,
            100,
            30,
            120,
        ),
        _linha_parte2(
            "B - RECEITAS RECEBIDAS DO FUNDEB", 200, 300, 400, 500, 600
        ),
        _linha_parte2(
            "B - TOTAL DAS DESPESAS CUSTEADAS COM RECURSOS DO FUNDEB "
            "RECEBIDAS NO EXERCÍCIO",
            150,
            260,
            330,
            440,
            500,
        ),
        _linha_parte2(
            "D - Restos a Pagar Cancelados (RPP e RPNP) Inscritos em 2025",
            60,
            70,
            80,
            90,
            100,
        ),
        _linha_parte2(
            "D - EXCESSO APLICADO EM EDUCAÇÃO - Inscritos em 2025",
            10,
            20,
            90,
            40,
            120,
        ),
        _linha_parte2(
            "D - Restos a Pagar Cancelados (RPP e RPNP) Inscritos em 2024",
            15,
            20,
            25,
            30,
            35,
        ),
        _linha_parte2(
            "D - EXCESSO APLICADO EM EDUCAÇÃO - Inscritos em 2024",
            5,
            30,
            10,
            40,
            5,
        ),
        _linha_parte2(
            "C - RP Cancelado TAC - Inscritos em 2016", 1, 2, 3, 4, 5
        ),
        _linha_parte2(
            "C - RP Cancelado TAC - Inscritos em 2017", 6, 7, 8, 9, 10
        ),
        _linha_parte2("(-) Outra despesa não computável", 3, 4, 5, 6, 7),
        _linha_parte2(
            "VALOR TOTAL DESTINADO A APLICAÇÃO EM EDUCAÇÃO (II)",
            800,
            987,
            1039,
            1171,
            1218,
        ),
    ]


class TestNumeroDecimal(unittest.TestCase):
    def test_aceita_formatos_pt_br_e_da_api_sem_float_financeiro(self) -> None:
        casos = {
            "5.194.807.180,76": Decimal("5194807180.76"),
            "R$ 1.234,56": Decimal("1234.56"),
            "(1.234,56)": Decimal("-1234.56"),
            "1.234,56-": Decimal("-1234.56"),
            "38,09%": Decimal("38.09"),
            "5194807180.76": Decimal("5194807180.76"),
            "1,234.56": Decimal("1234.56"),
            42: Decimal("42"),
            42.5: Decimal("42.5"),
            None: Decimal("0"),
            "": Decimal("0"),
        }

        for recebido, esperado in casos.items():
            with self.subTest(recebido=recebido):
                self.assertEqual(numero_decimal(recebido), esperado)

        with self.assertRaisesRegex(ValueError, "booleano"):
            numero_decimal(True)


class TestParte1Referencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dados = ler_csv_parte1(ARQUIVO_PARTE1)

    def test_usa_cabecalho_amarelo_e_recompoe_base_e_minimo(self) -> None:
        self.assertEqual(
            tuple(self.dados[0]),
            (
                "descricao",
                "Receita Prevista",
                "Receita Arrecadada",
                "Diferença (B-A)",
                "Arrecadada/Prevista",
            ),
        )
        self.assertNotIn("R$", self.dados[0])

        resultado = calcular_parte1(self.dados)

        self.assertEqual(len(resultado.componentes), 5)
        self.assertEqual(resultado.base_prevista, Decimal("68954885139.67"))
        self.assertEqual(resultado.base_arrecadada, Decimal("25852525422.83"))
        self.assertEqual(resultado.diferenca_receita, Decimal("-43102359716.84"))
        self.assertEqual(resultado.minimo_sobre_prevista, Decimal("17238721284.92"))
        self.assertEqual(resultado.minimo_sobre_arrecadada, Decimal("6463131355.71"))
        self.assertEqual(resultado.diferenca_minimo, Decimal("-10775589929.21"))
        self.assertEqual(
            resultado.realizacao_percentual.quantize(Decimal("0.01")),
            Decimal("37.49"),
        )
        self.assertEqual(resultado.avisos, ())

    def test_aceita_cabecalhos_efetivos_da_consulta_084835(self) -> None:
        descricao = "Receitas Consideradas para fins de Limite Contitucional"
        dados = [
            {
                descricao: "(+) Impostos",
                "Receita Prevista (A)": "100,00",
                "Receita Arrecadada (B)": "80,00",
                "Diferença (B-A)": "-20,00",
                "Arrecadada/Prevista": "80,00",
            },
            {
                descricao: "(-) Transferências aos Municípios",
                "Receita Prevista (A)": "-20,00",
                "Receita Arrecadada (B)": "-10,00",
                "Diferença (B-A)": "10,00",
                "Arrecadada/Prevista": "50,00",
            },
            {
                descricao: "TOTAL - BASE DE CÁLCULO",
                "Receita Prevista (A)": "80,00",
                "Receita Arrecadada (B)": "70,00",
                "Diferença (B-A)": "-10,00",
                "Arrecadada/Prevista": "87,50",
            },
            {
                descricao: "VALOR A SER APLICADO EM EDUCAÇÃO (25% DA RECEITA)",
                "Receita Prevista (A)": "20,00",
                "Receita Arrecadada (B)": "17,50",
                "Diferença (B-A)": "-2,50",
                "Arrecadada/Prevista": "87,50",
            },
        ]

        resultado = calcular_parte1(dados)

        self.assertEqual(resultado.base_prevista, Decimal("80.00"))
        self.assertEqual(resultado.base_arrecadada, Decimal("70.00"))
        self.assertEqual(resultado.minimo_sobre_prevista, Decimal("20.00"))
        self.assertEqual(resultado.minimo_sobre_arrecadada, Decimal("17.50"))
        self.assertEqual(resultado.avisos, ())

    def test_payload_ao_vivo_com_descricao_e_apenas_r_nao_perde_dados_silenciosamente(self) -> None:
        descricao = "Receitas Consideradas para fins de Limite Contitucional"
        payload_parte1 = [
            {descricao: "Receita Prevista", "R$": "Arrecadada/Prevista"},
            {descricao: "(+) Impostos", "R$": "38,09"},
            {descricao: "TOTAL - BASE DE CÁLCULO", "R$": "37,49"},
        ]

        with self.assertRaises(ErroSchemaFlexvision) as contexto:
            calcular_parte1(payload_parte1)

        mensagem = str(contexto.exception)
        self.assertIn("consulta da Parte 1", mensagem)
        self.assertIn("'R$' repetidos", mensagem)
        self.assertIn("Receita Prevista", mensagem)
        self.assertIn("Receita Arrecadada", mensagem)
        self.assertIn("última chave 'R$'", mensagem)
        self.assertIn("não podem ser inferidas", mensagem)

    def test_mapeia_colunas_r_sufixadas_pela_linha_visual_amarela(self) -> None:
        descricao = "Receitas Consideradas para fins de Limite Contitucional"
        payload_parte1 = [
            {
                descricao: descricao,
                "R$": "Receita Prevista",
                "R$_1": "Receita Arrecadada",
                "R$_2": "Diferença (B-A)",
                "R$_3": "Arrecadada/Prevista",
            },
            {
                descricao: "(+) Impostos",
                "R$": "100,00",
                "R$_1": "80,00",
                "R$_2": "-20,00",
                "R$_3": "80,00",
            },
            {
                descricao: "(-) Transferências aos Municípios",
                "R$": "-20,00",
                "R$_1": "-10,00",
                "R$_2": "10,00",
                "R$_3": "50,00",
            },
            {
                descricao: "TOTAL - BASE DE CÁLCULO",
                "R$": "80,00",
                "R$_1": "70,00",
                "R$_2": "-10,00",
                "R$_3": "87,50",
            },
            {
                descricao: "VALOR A SER APLICADO EM EDUCAÇÃO (25% DA RECEITA)",
                "R$": "20,00",
                "R$_1": "17,50",
                "R$_2": "-2,50",
                "R$_3": "87,50",
            },
        ]

        resultado = calcular_parte1(payload_parte1)

        self.assertEqual(len(resultado.componentes), 2)
        self.assertEqual(resultado.base_prevista, Decimal("80.00"))
        self.assertEqual(resultado.base_arrecadada, Decimal("70.00"))
        self.assertEqual(resultado.minimo_sobre_prevista, Decimal("20.00"))
        self.assertEqual(resultado.minimo_sobre_arrecadada, Decimal("17.50"))

    def test_total_informado_e_opcional(self) -> None:
        dados = [
            {
                "Descrição": "(+) Impostos",
                "Receita Prevista": "100,00",
                "Receita Arrecadada": "80,00",
            },
            {
                "Descrição": "(-) Transferências aos Municípios",
                "Receita Prevista": "-20,00",
                "Receita Arrecadada": "-10,00",
            },
        ]

        resultado = calcular_parte1(dados)

        self.assertEqual(resultado.base_prevista, Decimal("80.00"))
        self.assertEqual(resultado.base_arrecadada, Decimal("70.00"))
        self.assertIn("não veio no retorno", resultado.avisos[0])


class TestParte2AdaptadaReferencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dados_brutos = ler_csv_parte2(ARQUIVO_PARTE2_BRUTO)
        cls.dados_consolidados = ler_csv_parte2(ARQUIVO_PARTE2_CONSOLIDADO)
        cls.dados_original = ler_csv_parte2(ARQUIVO_PARTE2_ORIGINAL)
        cls.resultado = calcular_parte2(cls.dados_brutos)
        cls.resultado_consolidado = calcular_parte2(
            cls.dados_consolidados,
            aceitar_consolidados=True,
        )

    def test_recalcula_parte2_bruta_e_confere_total_consolidado(self) -> None:
        esperado_total = {
            "dotacao_atual": Decimal("10652809036.97"),
            "despesa_autorizada": Decimal("9735697854.66"),
            "despesa_empenhada": Decimal("6276741394.65"),
            "despesa_liquidada": Decimal("6037355107.77"),
            "despesa_paga": Decimal("5915601500.84"),
        }

        self.assertEqual(self.resultado.total_aplicado, esperado_total)
        for atributo in (
            "valores_positivos",
            "redutor_a",
            "redutor_b",
            "redutor_c",
            "redutor_d",
            "outras_deducoes",
            "total_aplicado",
        ):
            with self.subTest(atributo=atributo):
                self.assertEqual(
                    getattr(self.resultado, atributo),
                    getattr(self.resultado_consolidado, atributo),
                )
        self.assertEqual(
            self.resultado.redutor_b,
            {
                "dotacao_atual": Decimal("0.00"),
                "despesa_autorizada": Decimal("0.00"),
                "despesa_empenhada": Decimal("58377935.29"),
                "despesa_liquidada": Decimal("58377935.29"),
                "despesa_paga": Decimal("117624716.38"),
            },
        )
        for redutor in (
            self.resultado.redutor_a,
            self.resultado.redutor_c,
            self.resultado.redutor_d,
        ):
            self.assertTrue(all(valor == 0 for valor in redutor.values()))
        self.assertEqual(
            self.resultado.outras_deducoes["despesa_liquidada"],
            Decimal("112563686.12"),
        )
        self.assertEqual(
            self.resultado.valor("despesa_liquidada"), Decimal("6037355107.77")
        )
        self.assertEqual(len(self.resultado.detalhes_a), 2)
        self.assertEqual(len(self.resultado.detalhes_c), 9)

    def test_consolidado_exige_opt_in_e_nao_substitui_insumos_brutos(self) -> None:
        with self.assertRaisesRegex(ErroSchemaFlexvision, "quatro insumos brutos"):
            calcular_parte2(self.dados_consolidados)

    def test_monta_relatorio_calculado_no_formato_do_original(self) -> None:
        calculado = self.resultado.relatorio_calculado()
        coluna_descricao_original = next(iter(self.dados_original[0]))

        self.assertEqual(len(calculado), len(self.dados_original))
        for indice, (recebido, esperado) in enumerate(
            zip(calculado, self.dados_original)
        ):
            with self.subTest(linha=indice, descricao=recebido["descricao"]):
                self.assertEqual(
                    normalizar_texto(recebido["descricao"]),
                    normalizar_texto(esperado[coluna_descricao_original]),
                )
                for estagio, coluna in COLUNAS_PARTE2.items():
                    valor_esperado = numero_decimal(esperado[coluna])
                    precisao_original = Decimal(1).scaleb(
                        valor_esperado.as_tuple().exponent
                    )
                    self.assertEqual(
                        recebido[estagio].quantize(
                            precisao_original,
                            rounding=ROUND_HALF_UP,
                        ),
                        valor_esperado,
                    )

    def test_recalcula_total_fundeb_pelo_filtro_com_os_valores_reais(self) -> None:
        dados_com_filtro: list[dict[str, object]] = []
        for registro_original in self.dados_brutos:
            registro = dict(registro_original)
            coluna_descricao = next(iter(registro))
            if (
                "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
                in str(registro[coluna_descricao])
            ):
                registro[coluna_descricao] = (
                    "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO"
                )
                for coluna in COLUNAS_PARTE2.values():
                    registro[coluna] = -numero_decimal(registro[coluna])
            dados_com_filtro.append(registro)

        resultado = calcular_parte2(dados_com_filtro)

        for atributo in (
            "valores_positivos",
            "redutor_a",
            "redutor_b",
            "redutor_c",
            "redutor_d",
            "outras_deducoes",
            "total_aplicado",
        ):
            with self.subTest(atributo=atributo):
                self.assertEqual(
                    getattr(resultado, atributo),
                    getattr(self.resultado, atributo),
                )
        self.assertEqual(
            resultado.total_aplicado["despesa_liquidada"],
            Decimal("6037355107.77"),
        )
        self.assertFalse(
            any(
                "FUNDEB-FILTRO" in str(linha["descricao"])
                for linha in resultado.relatorio_calculado()
            )
        )


class TestParte2Bruta(unittest.TestCase):
    def test_calcula_total_transferido_ao_fundeb_pelo_no_filtro(self) -> None:
        dados = [
            linha
            for linha in _fixture_parte2_bruta()
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
            not in str(linha["Descrição"])
        ]
        dados.append(
            _linha_parte2(
                "(+) INSUMO FUNDEB-FILTRO",
                -50,
                -60,
                -70,
                -80,
                -90,
            )
        )

        resultado = calcular_parte2(dados, validar_total_final=False)

        self.assertEqual(
            resultado.valores_positivos,
            {
                "dotacao_atual": Decimal("1050.00"),
                "despesa_autorizada": Decimal("1160.00"),
                "despesa_empenhada": Decimal("1270.00"),
                "despesa_liquidada": Decimal("1380.00"),
                "despesa_paga": Decimal("1490.00"),
            },
        )
        descricoes_relatorio = [
            linha["descricao"] for linha in resultado.relatorio_calculado()
        ]
        self.assertIn(
            "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
            descricoes_relatorio,
        )
        self.assertFalse(
            any("FUNDEB-FILTRO" in descricao for descricao in descricoes_relatorio)
        )

    def test_insumo_fundeb_filtro_deve_ter_sinal_compativel_com_zero_menos(self) -> None:
        dados = [
            linha
            for linha in _fixture_parte2_bruta()
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
            not in str(linha["Descrição"])
        ]
        dados.append(
            _linha_parte2(
                "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO",
                50,
                50,
                50,
                50,
                50,
            )
        )

        with self.assertRaisesRegex(ErroRegraNegocio, "0 - valor"):
            calcular_parte2(dados, validar_total_final=False)

    def test_total_direto_e_filtro_iguais_nao_sao_somados_duas_vezes(self) -> None:
        dados = _fixture_parte2_bruta()
        total_direto = next(
            linha
            for linha in dados
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
            in str(linha["Descrição"])
        )
        for coluna in COLUNAS_PARTE2.values():
            total_direto[coluna] = 50
        dados.append(
            _linha_parte2(
                "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO",
                -50,
                -50,
                -50,
                -50,
                -50,
            )
        )

        resultado = calcular_parte2(dados, validar_total_final=False)

        self.assertEqual(
            resultado.valores_positivos["despesa_liquidada"],
            Decimal("1350.00"),
        )
        descricoes = [
            linha["descricao"] for linha in resultado.relatorio_calculado()
        ]
        self.assertEqual(
            sum(
                "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB" in descricao
                for descricao in descricoes
            ),
            1,
        )

    def test_total_direto_e_filtro_divergentes_sao_rejeitados(self) -> None:
        dados = _fixture_parte2_bruta()
        dados.append(
            _linha_parte2(
                "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO",
                -50,
                -50,
                -50,
                -50,
                -50,
            )
        )

        with self.assertRaisesRegex(ErroRegraNegocio, "Divergência.*FUNDEB"):
            calcular_parte2(dados, validar_total_final=False)

    def test_total_transferido_ao_fundeb_e_obrigatorio(self) -> None:
        dados = [
            linha
            for linha in _fixture_parte2_bruta()
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
            not in str(linha["Descrição"])
        ]

        with self.assertRaisesRegex(
            ErroSchemaFlexvision,
            "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB",
        ):
            calcular_parte2(dados, validar_total_final=False)

    def test_total_transferido_exige_marcador_positivo(self) -> None:
        dados = _fixture_parte2_bruta()
        total_fundeb = next(
            linha
            for linha in dados
            if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
            in str(linha["Descrição"])
        )
        total_fundeb["Descrição"] = "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"

        with self.assertRaisesRegex(ErroSchemaFlexvision, "positiva.*\\(\\+\\)"):
            calcular_parte2(dados, validar_total_final=False)

    def test_redutor_a_liquidado_e_recalculado_pelos_quatro_insumos_reais(self) -> None:
        dados = _fixture_parte2_bruta()
        valores_liquidados = {
            "SUPERAVIT FINANCEIRO DOS RECURSOS TRANSFERIDOS DO FUNDEB-IMPOSTOS":
                "4.585.413,00",
            "APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO ANTERIOR-IMPOSTOS":
                "28.296.302,99",
            "SUPERAVIT FINANCEIRO DOS RECURSOS TRANSFERIDOS DO FUNDEB-COMPLEMENTAÇÃO":
                "2.968.357,32",
            "APLICAÇÃO DO SUPERÁVIT DO FUNDEB DO EXERCÍCIO ANTERIOR-COMPLEMENTAÇÃO":
                "5.144.462,03",
        }
        for linha in dados:
            for trecho, valor in valores_liquidados.items():
                if trecho in str(linha["Descrição"]):
                    linha["Despesa Liquidada"] = valor

        resultado = calcular_parte2(dados, validar_total_final=False)

        self.assertEqual(resultado.redutor_a["despesa_liquidada"], Decimal("0.00"))
        self.assertTrue(
            all(
                detalhe["despesa_liquidada"] == 0
                for detalhe in resultado.detalhes_a
            )
        )

    def test_aplica_formulas_a_b_c_d_por_estagio_e_classifica_pelo_significado(self) -> None:
        resultado = calcular_parte2(_fixture_parte2_bruta())

        self.assertEqual(
            resultado.redutor_a,
            dict(zip(ESTAGIOS_DESPESA, map(Decimal, ("100", "40", "100", "50", "90")))),
        )
        self.assertEqual(
            resultado.redutor_b,
            dict(zip(ESTAGIOS_DESPESA, map(Decimal, ("30", "10", "30", "10", "40")))),
        )
        self.assertEqual(
            resultado.redutor_c,
            dict(zip(ESTAGIOS_DESPESA, map(Decimal, ("60", "50", "15", "50", "30")))),
        )
        self.assertEqual(
            resultado.redutor_d,
            dict(zip(ESTAGIOS_DESPESA, map(Decimal, ("7", "9", "11", "13", "15")))),
        )
        self.assertEqual(
            resultado.outras_deducoes,
            dict(zip(ESTAGIOS_DESPESA, map(Decimal, ("3", "4", "5", "6", "7")))),
        )
        self.assertEqual(
            resultado.total_aplicado,
            dict(
                zip(
                    ESTAGIOS_DESPESA,
                    map(Decimal, ("800", "987", "1039", "1171", "1218")),
                )
            ),
        )

        detalhes_c = {
            detalhe["exercicio_inscricao"]: detalhe for detalhe in resultado.detalhes_c
        }
        self.assertEqual(set(detalhes_c), {2024, 2025})
        self.assertEqual(detalhes_c[2024]["despesa_liquidada"], Decimal("0"))
        self.assertEqual(detalhes_c[2025]["despesa_liquidada"], Decimal("50"))
        self.assertEqual(
            {detalhe["grupo"] for detalhe in resultado.detalhes_a},
            {"impostos", "complementacao_uniao"},
        )

    def test_coluna_ausente_em_uma_linha_nao_vira_zero_silenciosamente(self) -> None:
        dados = _fixture_parte2_bruta()
        del dados[0]["Despesa Liquidada"]

        with self.assertRaisesRegex(ErroSchemaFlexvision, "não possui a coluna"):
            calcular_parte2(dados)

    def test_descricao_ausente_em_uma_linha_nao_e_ignorada(self) -> None:
        dados = _fixture_parte2_bruta()
        del dados[0]["Descrição"]

        with self.assertRaisesRegex(ErroSchemaFlexvision, "coluna de descrição"):
            calcular_parte2(dados)


class TestMetricasRecalculadas(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resultado = calcular_indice_educacao(
            ler_csv_parte1(ARQUIVO_PARTE1),
            ler_csv_parte2(ARQUIVO_PARTE2_BRUTO),
        )

    def test_entrega_metricas_do_dashboard_pela_despesa_liquidada(self) -> None:
        metricas = self.resultado.metricas_dashboard()

        self.assertEqual(metricas["estagio"], "despesa_liquidada")
        self.assertEqual(metricas["receita_arrecadada"], Decimal("25852525422.83"))
        self.assertEqual(metricas["minimo_constitucional"], Decimal("6463131355.71"))
        self.assertEqual(metricas["aplicacao_educacao"], Decimal("6037355107.77"))
        self.assertEqual(metricas["saldo_para_minimo"], Decimal("-425776247.94"))
        self.assertEqual(metricas["deficit_para_minimo"], Decimal("425776247.94"))
        self.assertEqual(metricas["excedente_sobre_minimo"], Decimal("0"))
        self.assertEqual(
            metricas["indice_aplicacao_percentual"].quantize(Decimal("0.0001")),
            Decimal("23.3531"),
        )
        self.assertEqual(
            metricas["margem_pontos_percentuais"].quantize(Decimal("0.0001")),
            Decimal("-1.6469"),
        )
        self.assertEqual(
            metricas["atingimento_do_minimo_percentual"].quantize(Decimal("0.0001")),
            Decimal("93.4122"),
        )
        self.assertFalse(metricas["atingiu_minimo"])

    def test_entrega_acompanhamento_anual_sobre_a_receita_prevista(self) -> None:
        metricas = self.resultado.metricas_dashboard("despesa_liquidada")

        self.assertEqual(
            metricas["minimo_constitucional_previsto"],
            Decimal("17238721284.92"),
        )
        self.assertEqual(
            metricas["indice_sobre_receita_prevista_percentual"].quantize(
                Decimal("0.0000000001")
            ),
            Decimal("8.7555147043"),
        )
        self.assertEqual(
            metricas["atingimento_do_minimo_previsto_percentual"].quantize(
                Decimal("0.0000000001")
            ),
            Decimal("35.0220588174"),
        )
        self.assertEqual(
            metricas["saldo_para_minimo_previsto"],
            Decimal("-11201366177.15"),
        )
        self.assertEqual(
            metricas["deficit_para_minimo_previsto"],
            Decimal("11201366177.15"),
        )
        self.assertEqual(metricas["excedente_sobre_minimo_previsto"], Decimal("0"))
        self.assertFalse(metricas["atingiu_minimo_previsto"])

    def test_visao_anual_fica_indisponivel_quando_a_base_prevista_e_zero(
        self,
    ) -> None:
        parte1 = replace(
            self.resultado.parte1,
            base_prevista=Decimal("0"),
            minimo_sobre_prevista=Decimal("0"),
        )
        resultado = replace(self.resultado, parte1=parte1)

        metricas = resultado.metricas_dashboard("despesa_liquidada")

        self.assertEqual(metricas["minimo_constitucional_previsto"], Decimal("0"))
        self.assertIsNone(metricas["indice_sobre_receita_prevista_percentual"])
        self.assertIsNone(metricas["atingimento_do_minimo_previsto_percentual"])
        self.assertFalse(metricas["atingiu_minimo_previsto"])

    def test_meta_anual_exatamente_atingida_nao_tem_saldo(self) -> None:
        total_aplicado = dict(self.resultado.parte2.total_aplicado)
        total_aplicado["despesa_liquidada"] = (
            self.resultado.parte1.minimo_sobre_prevista
        )
        resultado = replace(
            self.resultado,
            parte2=replace(self.resultado.parte2, total_aplicado=total_aplicado),
        )

        metricas = resultado.metricas_dashboard("despesa_liquidada")

        self.assertEqual(
            metricas["atingimento_do_minimo_previsto_percentual"], Decimal("100")
        )
        self.assertEqual(metricas["saldo_para_minimo_previsto"], Decimal("0.00"))
        self.assertEqual(metricas["deficit_para_minimo_previsto"], Decimal("0"))
        self.assertEqual(metricas["excedente_sobre_minimo_previsto"], Decimal("0"))
        self.assertTrue(metricas["atingiu_minimo_previsto"])

    def test_um_centavo_abaixo_da_meta_anual_continua_como_deficit(self) -> None:
        total_aplicado = dict(self.resultado.parte2.total_aplicado)
        total_aplicado["despesa_liquidada"] = (
            self.resultado.parte1.minimo_sobre_prevista - Decimal("0.01")
        )
        resultado = replace(
            self.resultado,
            parte2=replace(self.resultado.parte2, total_aplicado=total_aplicado),
        )

        metricas = resultado.metricas_dashboard("despesa_liquidada")

        self.assertLess(
            metricas["atingimento_do_minimo_previsto_percentual"], Decimal("100")
        )
        self.assertEqual(metricas["saldo_para_minimo_previsto"], Decimal("-0.01"))
        self.assertEqual(metricas["deficit_para_minimo_previsto"], Decimal("0.01"))
        self.assertEqual(metricas["excedente_sobre_minimo_previsto"], Decimal("0"))
        self.assertFalse(metricas["atingiu_minimo_previsto"])


if __name__ == "__main__":
    unittest.main()
