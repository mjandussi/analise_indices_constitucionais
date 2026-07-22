"""Testes do contrato CSV entre a extração e a ETL."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from app_educacao.dados import ler_csv, processar_snapshot, processar_ultimo_snapshot
from app_educacao.extracao import persistir_dados_educacao
from indices_constitucionais.fontes import ler_csv_parte1, ler_csv_parte2
from indices_constitucionais.normalizacao import normalizar_texto, numero_decimal


RAIZ = Path(__file__).resolve().parents[1]
CONSULTAS = RAIZ / "consultas_base"


def _arquivo_unico(padrao: str) -> Path:
    encontrados = list(CONSULTAS.glob(padrao))
    if len(encontrados) != 1:
        raise AssertionError(f"Esperado um arquivo para {padrao}.")
    return encontrados[0]


def _payloads_homologados() -> dict[str, object]:
    parte1 = ler_csv_parte1(_arquivo_unico("*Parte 1_3 (2026)_*.csv"))
    parte2 = deepcopy(
        ler_csv_parte2(
            _arquivo_unico("*Parte 2_3 (2026) com FR 108 Adaptado_*.csv")
        )
    )
    coluna_descricao = next(iter(parte2[0]))
    linha_fundeb = next(
        linha
        for linha in parte2
        if "TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB"
        in normalizar_texto(linha[coluna_descricao])
    )
    parte2.remove(linha_fundeb)
    linha_fundeb[coluna_descricao] = (
        "(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO"
    )
    for coluna in list(linha_fundeb)[1:]:
        linha_fundeb[coluna] = str(-numero_decimal(linha_fundeb[coluna]))
    parte2.append(linha_fundeb)
    return {"parte1": parte1, "parte2": parte2}


class TestPipelineCsv(unittest.TestCase):
    def test_etl_consume_os_dois_csvs_e_reproduz_resultado_homologado(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            pasta_raiz = Path(temporaria)
            snapshot = persistir_dados_educacao(
                _payloads_homologados(),
                2026,
                4,
                pasta_saida=pasta_raiz,
            )

            # O leitor não infere float; a normalização financeira ocorre na ETL.
            primeira_celula = next(iter(ler_csv(snapshot / "parte1.csv")[0].values()))
            self.assertIsInstance(primeira_celula, str)

            # As cópias JSON são apenas evidência da extração. Torná-las
            # ilegíveis não pode afetar a ETL, cuja entrada são os CSVs.
            (snapshot / "parte1.json").write_text("JSON inválido", encoding="utf-8")
            (snapshot / "parte2.json").write_text("JSON inválido", encoding="utf-8")

            resultado = processar_snapshot(snapshot)
            self.assertEqual(
                resultado["parte1"]["base_arrecadada"],
                Decimal("25852525422.83"),
            )
            self.assertEqual(
                resultado["parte2"]["total_aplicado"]["despesa_liquidada"],
                Decimal("6037355107.77"),
            )

            mais_recente = processar_ultimo_snapshot(
                2026,
                4,
                pasta_dados=pasta_raiz,
            )
            self.assertEqual(
                mais_recente["parte2"]["total_aplicado"],
                resultado["parte2"]["total_aplicado"],
            )


if __name__ == "__main__":
    unittest.main()
