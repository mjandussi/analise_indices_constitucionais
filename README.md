# Índice constitucional de educação

Biblioteca de transformação das consultas Flexvision em métricas prontas para
um dashboard Streamlit sobre a aplicação mínima de 25% em educação.

O projeto mantém a extração, a normalização e as regras de negócio fora da
interface. Assim, o Streamlit apenas escolhe exercício/período, chama o
pipeline e apresenta os objetos de resultado.

## O que o pipeline calcula

- **Parte 1 — consulta 084835:** base de receita prevista e arrecadada, mínimo
  constitucional de 25%, diferença e percentual de realização da receita.
- **Parte 2 — consulta 084837:** valores positivos aplicados em educação,
  redutores A a D, outras deduções e total efetivamente aplicado em cada
  estágio da despesa.
- **Indicadores finais:** índice aplicado sobre a receita arrecadada, margem em
  pontos percentuais para 25%, déficit ou excedente e situação de atingimento.

Os cálculos financeiros usam `Decimal`; valores brasileiros como
`5.194.807.180,76` são normalizados sem passar por `float`.

## Instalação local

Com o ambiente virtual ativado, instale este projeto, o dashboard e o client
SIAFE-Rio:

```powershell
python -m pip install -e ".[dashboard]"
python -m pip install -e "..\client_api_siaferio[all]"
```

Configure um `.env` não versionado:

```env
SIAFE_USUARIO=seu_usuario
SIAFE_SENHA=sua_senha
```

## Executar o dashboard

### Versão didática, somente API

O arquivo `app_edu.py` reúne em um único ponto de entrada a consulta, a
normalização, os cálculos A–D, as métricas e a apresentação. Ele não possui
seletor de fonte nem fallback para CSV:

```powershell
python -m streamlit run app_edu.py
```

O código está dividido em oito seções numeradas para leitura sequencial. Na
própria tela, a aba **Memória de cálculo para apresentação à equipe** mostra a
fórmula preenchida com os valores, a abertura de A–D, os componentes da receita
e a rastreabilidade das consultas 084835 e 084837.

### Versão completa com referência offline

```powershell
python -m streamlit run app.py
```

O aplicativo abre inicialmente no modo **CSV de referência**, que funciona
offline e permite validar imediatamente cards, gráficos e memórias de cálculo.
No controle **Fonte dos dados**, selecione **API Flexvision** para consultar um
exercício/período após os ajustes das consultas 084835 e 084837.

A referência offline usa a Parte 2 **FR 108 Adaptado**, que contém os insumos
brutos. O pipeline calcula A, B, C e D em Python; o CSV sem “Adaptado”, no qual
essas linhas já vêm prontas, é mantido somente como gabarito de reconciliação
nos testes e não alimenta o dashboard.

O dashboard inclui:

- índice, aplicação, mínimo constitucional e déficit/excedente;
- dois relógios: índice sobre a arrecadação do período e índice sobre a
  previsão anual, ambos com referência de 25%;
- visão gerencial da meta anual prevista, incluindo execução percentual e
  saldo para os 25% da receita prevista;
- comparação entre despesa empenhada, liquidada e paga com a linha de 25%;
- abertura dos redutores A–D e demais deduções;
- relatório pós-cálculo no mesmo leiaute lógico do CSV ORIGINAL, mantendo os
  insumos brutos em uma abertura separada para auditoria;
- componentes da base de receita;
- memórias do A por grupo e do C por exercício, tanto no CSV adaptado quanto
  na API; e
- tabela normalizada para auditoria.

A alteração do estágio não refaz a consulta. O resultado da API permanece
somente na sessão atual do Streamlit por até 15 minutos e é invalidado na
próxima interação se fonte, exercício, período ou credenciais mudarem. Ao sair
do modo API, o snapshot é descartado. Usuário, senha, client e token não são
armazenados no estado da página.

Na referência de abril/2026, a despesa liquidada de R$ 6,04 bilhões representa
8,76% da receita prevista de R$ 68,95 bilhões e 35,02% da meta anual prevista
de R$ 17,24 bilhões. Essa visão projetada é exibida separadamente da apuração
do período sobre a receita arrecadada.

## Uso com `SiafeAPI`

```python
import os

from dotenv import load_dotenv
from siaferio import SiafeAPI

from indices_constitucionais import consultar_e_calcular_educacao


load_dotenv()

with SiafeAPI(
    usuario=os.environ["SIAFE_USUARIO"],
    senha=os.environ["SIAFE_SENHA"],
) as api:
    resultado = consultar_e_calcular_educacao(
        api,
        exercicio=2026,
        periodo=4,
        estagio_indice="despesa_liquidada",
        timeout=300,
    )

metricas = resultado.metricas_dashboard()
print(metricas["indice_aplicacao_percentual"])
print(metricas["atingiu_minimo"])
```

O estágio padrão do índice é `despesa_liquidada`. Também estão disponíveis
`dotacao_atual`, `despesa_autorizada`, `despesa_empenhada` e `despesa_paga`.

## Exemplo mínimo no Streamlit

```python
import streamlit as st

from indices_constitucionais import formatar_brl, formatar_percentual


metricas = resultado.metricas_dashboard()
margem = metricas["margem_pontos_percentuais"]
margem_pp = "—" if margem is None else f"{margem:.2f} p.p.".replace(".", ",")

st.metric(
    "Índice aplicado",
    formatar_percentual(metricas["indice_aplicacao_percentual"]),
    margem_pp,
)
st.metric("Aplicação em educação", formatar_brl(metricas["aplicacao_educacao"]))
st.metric("Mínimo constitucional", formatar_brl(metricas["minimo_constitucional"]))
st.dataframe(resultado.parte2.quadro_resumo(), width="stretch")
```

## Contrato das consultas e pendência antes do uso ao vivo

1. A **084835** substitui a antiga 084779, cujos cabeçalhos `R$` repetidos
   colidiam no JSON. A cópia corrigida deve retornar os aliases efetivos e
   únicos `Receita Prevista (A)`, `Receita Arrecadada (B)`, `Diferença (B-A)`
   e `Arrecadada/Prevista`. As antigas linhas visuais com `R$`, `(A)`, `(B)`,
   `(C)` e `(B/A)` não são dados e são desconsideradas pelo cálculo. Esse
   retorno foi validado ao vivo com sucesso para 2026/04.
2. Na **084837**, mantenha no retorno as quatro linhas brutas de A, as duas de
   B, os pares anuais RP/excesso de C e os RPs TAC de D. A expressão agregada
   `(I) - (II)` e as demais fórmulas consolidadas não são necessárias, pois
   A–D são calculados em Python. O HTTP 500 auditado foi causado pela avaliação
   do `SE(...)` da linha B na antiga 084805; a nova consulta deve manter
   apenas `RECEITAS RECEBIDAS DO FUNDEB` e `TOTAL DAS DESPESAS CUSTEADAS...`.
3. A **084837** deve conter a linha de nome exato
   **`(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO`**, com os valores
   contábeis negativos. O Python aplica `0 - valor do filtro` em cada estágio e
   substitui essa linha pela versão positiva antes da soma. A posição pode
   mudar, mas o código não procura nomes alternativos.

Esse contrato foi validado ao vivo com as consultas 084835 e 084837 para
2026/04. Erros HTTP 500/502/503/504 recebem até três tentativas curtas;
persistindo a falha, o diagnóstico identifica qual consulta não respondeu.

## Testes

Linux/WSL:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

Com o extra `dashboard` instalado, a mesma suíte também executa um teste
headless que abre a página e troca o estágio selecionado.

A arquitetura, todas as fórmulas e o contrato dos objetos estão detalhados em
[Docs/pipeline_indice_educacao.md](Docs/pipeline_indice_educacao.md).
