"""Componentes simples da aplicação didática do índice de educação.

Os módulos são importados explicitamente por responsabilidade, por exemplo
``from app_educacao.extracao import extrair_dados_educacao``. Manter o pacote
sem importações ávidas também permite executar a CLI sem abrir o client antes
da chamada: ``python -m app_educacao.extracao ANO PERIODO``.
"""
