# Pipeline do índice constitucional de educação

Este documento descreve como as consultas Flexvision 084835 e 084837 são
transformadas em métricas estáveis para o futuro dashboard Streamlit.

## Arquitetura

O fluxo foi dividido em cinco responsabilidades:

1. `flexvision.py` consulta as duas fontes com o mesmo exercício e período.
2. `normalizacao.py` extrai os registros do JSON e converte textos e números.
3. `educacao.py` recompõe a Parte 1, calcula os redutores A–D da Parte 2 e
   combina as duas partes.
4. `modelos.py` entrega objetos de resultado independentes do Streamlit.
5. O aplicativo Streamlit formata e apresenta as métricas, sem repetir regras
   financeiras.

```text
SiafeAPI / Flexvision
  ├── 084835 (receitas) ──> calcular_parte1 ──┐
  └── 084837 (aplicação) ─> calcular_parte2 ──┤
                                               └─> ResultadoEducacao
                                                     ├─> cards
                                                     ├─> tabelas
                                                     └─> gráficos Streamlit
```

Na aplicação modular, as mesmas duas respostas passam por uma interface de
arquivos antes do cálculo:

```text
app_educacao/extracao.py
  ├── 084835 (JSON) ──> parte1.csv ──┐
  └── 084837 (JSON) ──> parte2.csv ──┤
                                      └─> app_educacao/dados.py
                                            ├─> dash_indice.py
                                            └─> dash_projecao.py
```

Os CSVs são lidos integralmente como texto e só depois normalizados para
`Decimal`. O par é publicado de forma atômica em uma pasta de snapshot, com
exercício, período, IDs das consultas e horário registrados em
`metadados.json`.

As respostas aceitas podem ser uma lista de objetos, um `DataFrame` ou um
envelope JSON com uma única coleção de registros. Se um envelope contiver
mais de uma lista, a coleção correta deve ser selecionada explicitamente antes
do cálculo. Essa restrição evita usar silenciosamente uma lista errada.

Os valores monetários são tratados como `Decimal` e arredondados em centavos
com `ROUND_HALF_UP`. A normalização aceita números da API e formatos como
`R$ 1.234,56`, negativos e percentuais.

## Parte 1 — receita e mínimo de 25%

A Parte 1 usa somente as linhas de componentes identificadas por `(+)` e
`(-)`. Linhas de cabeçalho, separadores e cabeçalhos visuais como `R$`, `(A)`,
`(B)`, `(C)` e `(B/A)` não participam do cálculo.

Em cada componente, o sinal deve vir no próprio valor da consulta. Portanto,
uma linha `(-)` da Parte 1 deve possuir números negativos; o código não inverte
esse sinal novamente.

Para os componentes de receita `i`:

```text
base_prevista       = soma(receita_prevista_i)
base_arrecadada     = soma(receita_arrecadada_i)
diferenca_receita   = base_arrecadada - base_prevista
realizacao_percentual = 100 × base_arrecadada / base_prevista

minimo_sobre_prevista   = 25% × base_prevista
minimo_sobre_arrecadada = 25% × base_arrecadada
diferenca_minimo        = minimo_sobre_arrecadada - minimo_sobre_prevista
```

Como os valores aplicados são monetários, cada mínimo é elevado ao próximo
centavo (`ROUND_CEILING`). Isso impede que um arredondamento para baixo faça o
valor operacional representar menos que 25% da base. A formatação dos demais
valores monetários continua usando `ROUND_HALF_UP`.

Quando a base prevista for zero, o percentual de realização será `None`, pois
não existe divisão válida. Se as linhas `TOTAL - BASE DE CÁLCULO` e `VALOR A
SER APLICADO EM EDUCAÇÃO` vierem no retorno, seus valores são usados para
conferir o valor recomposto. Eles não substituem o cálculo.

## Parte 2 — aplicação efetiva em educação

As fórmulas são executadas separadamente para os cinco estágios:

| Chave | Estágio |
|---|---|
| `dotacao_atual` | Dotação atual |
| `despesa_autorizada` | Despesa autorizada |
| `despesa_empenhada` | Despesa empenhada |
| `despesa_liquidada` | Despesa liquidada |
| `despesa_paga` | Despesa paga |

### Valores positivos e outras deduções

`valores_positivos` é a soma das fontes cuja descrição começa por `(+)`.
`outras_deducoes` é a soma das demais linhas que começam por `(-)` e que não
são linhas agregadas dos redutores A–D.

Na Parte 2, essas deduções brutas são magnitudes positivas e são subtraídas na
fórmula final.

### Redutor A — superávit anterior não aplicado

O cálculo é feito separadamente para:

- impostos e transferências de impostos; e
- complementação da União.

Para cada grupo `g` e estágio de despesa:

```text
A_g = max(superavit_financeiro_g - aplicacao_do_superavit_g, 0)
A   = A_impostos + A_complementacao_uniao
```

Isto equivale à regra: se a aplicação do superávit for maior ou igual ao
superávit financeiro, o redutor é zero; caso contrário, reduz-se apenas a
parcela ainda não aplicada.

### Redutor B — FUNDEB não utilizado acima de 10%

```text
valor_nao_aplicado = receitas_recebidas_fundeb - despesas_custeadas_fundeb
limite_10_porcento = 10% × receitas_recebidas_fundeb
B = max(valor_nao_aplicado - limite_10_porcento, 0)
```

Assim, somente a parcela não aplicada que exceder 10% das receitas recebidas
do FUNDEB reduz a aplicação em educação.

### Redutor C — restos a pagar cancelados de MDE

As linhas são pareadas pelo exercício de inscrição. Linhas TAC ficam fora
deste grupo.

```text
C_ano = max(restos_cancelados_ano - excesso_aplicado_ano, 0)
C     = soma(C_ano para todos os exercícios encontrados)
```

Se não houver excesso correspondente em um exercício, ele é considerado
zero. Da mesma forma, um excesso sem RP cancelado não gera redutor negativo.

### Redutor D — restos a pagar cancelados do TAC

```text
D = soma(linhas de RP cancelado TAC de todos os exercícios)
```

A classificação de C e D é feita pelo conteúdo da descrição (`TAC`, `RPP`,
`RPNP`, `EXCESSO APLICADO`) e pelo ano, não apenas pela letra no começo da
linha. Isso é intencional: os prefixos C/D observados na consulta bruta estão
invertidos em relação ao documento da regra.

### Total aplicado

Para cada estágio:

```text
total_aplicado = valores_positivos
                 - redutor_A
                 - redutor_B
                 - redutor_C
                 - redutor_D
                 - outras_deducoes
```

Embora o título legado do relatório mostre `(I) - (II)`, esta implementação
segue a regra fornecida para o projeto: C e D são somados como redutores e,
portanto, ambos são subtraídos do total aplicado. Se a regra oficial for
alterada, essa decisão deve ser revista antes da publicação do dashboard.

Um total negativo é rejeitado como inconsistência. Se a consulta ainda
trouxer a linha `VALOR TOTAL DESTINADO A APLICAÇÃO EM EDUCAÇÃO`, ela serve
apenas para validar o valor recomposto em Python.

## Métricas constitucionais finais

O padrão é usar a despesa liquidada, mas o estágio pode ser configurado. Para
o estágio escolhido:

```text
aplicacao_educacao = total_aplicado_do_estagio
minimo_constitucional = minimo_sobre_arrecadada

indice_aplicacao_percentual = 100 × aplicacao_educacao / base_arrecadada
margem_pontos_percentuais   = indice_aplicacao_percentual - 25
saldo_para_minimo           = aplicacao_educacao - minimo_constitucional
deficit_para_minimo         = max(-saldo_para_minimo, 0)
excedente_sobre_minimo      = max(saldo_para_minimo, 0)
atingimento_do_minimo_percentual =
    100 × aplicacao_educacao / minimo_constitucional
atingiu_minimo = indice_aplicacao_percentual >= 25
```

Quando a base ou o mínimo for zero, o percentual que depender daquela divisão
será `None`.

### Visão gerencial da previsão anual

Além da apuração sobre a receita arrecadada, o dashboard acompanha a despesa
liquidada em relação à previsão do exercício:

```text
meta_anual_prevista = 25% × base_prevista
indice_sobre_receita_prevista = 100 × liquidado / base_prevista
atingimento_meta_anual = 100 × liquidado / meta_anual_prevista
saldo_meta_anual = liquidado - meta_anual_prevista
```

O índice sobre a previsão e o atingimento da meta são grandezas diferentes.
Na fixture de abril/2026, R$ 6,04 bilhões liquidados equivalem a 8,76% da
receita prevista total e a 35,02% da meta anual prevista de R$ 17,24 bilhões.
Essa leitura é gerencial e não substitui a apuração constitucional sobre a
receita efetivamente arrecadada.

## Extração e cálculo com `SiafeAPI`

O atalho `consultar_e_calcular_educacao` consulta os IDs padrão 084835 e
084837 com `parametros=[exercicio, periodo]`, na mesma sessão autenticada, e
retorna um `ResultadoEducacao`:

```python
import os

from dotenv import load_dotenv
from siaferio import SiafeAPI

from indices_constitucionais import consultar_e_calcular_educacao


load_dotenv()

usuario = os.getenv("SIAFE_USUARIO")
senha = os.getenv("SIAFE_SENHA")
if not usuario or not senha:
    raise RuntimeError("Defina SIAFE_USUARIO e SIAFE_SENHA no .env.")

with SiafeAPI(usuario=usuario, senha=senha) as api:
    resultado = consultar_e_calcular_educacao(
        api,
        exercicio=2026,
        periodo=4,
        estagio_indice="despesa_liquidada",
        timeout=300,
    )
```

IDs diferentes podem ser informados pelos argumentos `consulta_parte1` e
`consulta_parte2`. Se for necessário investigar ou guardar os payloads antes
de calcular, use `consultar_dados_educacao(...)` e depois
`calcular_indice_educacao(dados["parte1"], dados["parte2"])`.

Para conferência offline das exportações atualmente versionadas, os leitores
de CSV descartam os cabeçalhos visuais da Parte 1 e mantêm a tabela da Parte
2. A entrada operacional é o arquivo **FR 108 Adaptado**, com os insumos
brutos A–D:

```python
from indices_constitucionais import calcular_indice_educacao
from indices_constitucionais.fontes import ler_csv_parte1, ler_csv_parte2


parte1 = ler_csv_parte1("consultas_base/parte1.csv")
parte2 = ler_csv_parte2("consultas_base/parte2.csv")
resultado = calcular_indice_educacao(
    parte1,
    parte2,
)
```

Tanto no CSV adaptado quanto na API,
`aceitar_consolidados_parte2` permanece `False`. Assim, a linha A igual a zero
nunca é tomada como um dado pronto: o pipeline exige e compara os dois pares
de superávit/aplicação brutos. O mesmo princípio vale para B, C e D. A opção
`True` existe apenas para reconciliar, nos testes, a exportação antiga que não
contém mais seus insumos.

## Configuração do estágio

O estágio escolhido altera a aplicação usada no índice, mas não elimina os
demais valores do resultado:

```python
metricas_padrao = resultado.metricas_dashboard()
metricas_pagas = resultado.metricas_dashboard("despesa_paga")
todas_as_fases = resultado.metricas_por_estagio()
```

As opções aceitas são exatamente:

```python
(
    "dotacao_atual",
    "despesa_autorizada",
    "despesa_empenhada",
    "despesa_liquidada",
    "despesa_paga",
)
```

O estágio inicial deve ser definido conforme a regra adotada pelo relatório.
No pipeline, `despesa_liquidada` é apenas a configuração padrão; a escolha não
é apresentada como conclusão jurídica.

## Objetos prontos para o Streamlit

`ResultadoEducacao` concentra as duas partes:

- `resultado.metricas_dashboard()` fornece os cards do estágio selecionado;
- `resultado.metricas_por_estagio()` fornece uma série para comparação entre
  os cinco estágios;
- `resultado.parte1.metricas()` fornece os indicadores de receita;
- `resultado.parte1.componentes` permite auditar a formação das bases;
- `resultado.parte2.quadro_resumo()` fornece valores positivos, cada redutor,
  outras deduções e total aplicado;
- `resultado.parte2.relatorio_calculado()` substitui os insumos brutos de A–D
  pelas linhas consolidadas calculadas e recompõe o leiaute lógico do antigo
  relatório ORIGINAL;
- `resultado.parte2.detalhes_a` abre o redutor A por grupo;
- `resultado.parte2.detalhes_c` abre o redutor C por exercício;
- `resultado.parte2.linhas_normalizadas` preserva as linhas da Parte 2 para
  conferência.

Exemplo de apresentação sem recalcular a regra na página:

```python
import pandas as pd
import streamlit as st

from indices_constitucionais import formatar_brl, formatar_percentual


metricas = resultado.metricas_dashboard()

coluna_1, coluna_2, coluna_3 = st.columns(3)
coluna_1.metric(
    "Índice aplicado",
    formatar_percentual(metricas["indice_aplicacao_percentual"]),
)
coluna_2.metric(
    "Aplicação em educação",
    formatar_brl(metricas["aplicacao_educacao"]),
)
coluna_3.metric(
    "Mínimo de 25%",
    formatar_brl(metricas["minimo_constitucional"]),
)

st.dataframe(
    pd.DataFrame(resultado.parte2.quadro_resumo()),
    width="stretch",
)
st.dataframe(
    pd.DataFrame(resultado.metricas_por_estagio()),
    width="stretch",
)
```

As funções `formatar_brl` e `formatar_percentual` devem ser usadas somente na
camada visual. Gráficos e comparações devem continuar usando os valores
`Decimal` originais.

## Aplicativo Streamlit implementado

O arquivo `app.py` possui dois modos explícitos:

- **CSV de referência:** carrega a Parte 1 e o **FR 108 Adaptado**, exige os
  insumos brutos e recalcula A–D, identificando a página como referência
  offline;
- **API Flexvision:** lê as credenciais do `.env`, consulta 084835/084837 e
  exige os insumos brutos A–D. Uma falha da API nunca aciona o CSV como fallback
  silencioso.

O estágio é aplicado somente ao `ResultadoEducacao` já carregado. Portanto,
alternar entre dotação, autorizada, empenhada, liquidada e paga não abre uma
nova sessão nem repete as consultas.

Na comparação visual entre estágios, o painel mostra somente despesa
empenhada, liquidada e paga. Dotação atual e despesa autorizada continuam no
resultado técnico e no quadro completo para auditoria, mas não aparecem nesse
gráfico.

O snapshot da API fica isolado na sessão do navegador e tem validade de 15
minutos, verificada em cada reexecução da página. Ele é descartado ao trocar a
fonte, o exercício, o período, a versão do contrato ou as credenciais. Voltar
do CSV para a API exige uma nova consulta, evitando apresentar uma posição
antiga como atual.

A interface utiliza `Decimal` até o limite da camada visual. Tabelas monetárias
são enviadas ao Streamlit como strings formatadas; somente séries destinadas ao
Altair ou aos relógios Plotly são convertidas para `float`. A situação de
cumprimento continua sendo decidida pelo valor exato, não pelo percentual
arredondado exibido no card.

Para executar:

```powershell
python -m pip install -e ".[dashboard]"
python -m streamlit run app.py
```

## Limitações confirmadas nas consultas ao vivo

### 084835: cópia corrigida da antiga 084779

Na antiga 084779, o relatório possuía cabeçalhos visuais em mais de uma linha. Quando os vários
`R$` são usados como nomes de coluna, as chaves se repetem no JSON e uma
coluna sobrescreve a outra. Não há como recuperar Receita Prevista e Receita
Arrecadada depois que essa colisão já ocorreu no payload.

Por isso, a cópia 084835 foi criada com aliases/cabeçalhos efetivos e únicos:

- `Receita Prevista (A)`;
- `Receita Arrecadada (B)`;
- `Diferença (B-A)`; e
- `Arrecadada/Prevista`.

O retorno da 084835 foi validado ao vivo para 2026/04: chegaram nove registros
e as cinco colunas distintas, e o cálculo recompôs as bases prevista e
arrecadada sem depender das antigas linhas visuais.

Os cabeçalhos/linhas visuais `R$`, `(A)`, `(B)`, `(C)` e `(B/A)` podem
continuar existindo na apresentação da planilha, mas não devem ser as chaves
dos dados retornados pela API. Diferença e percentual são recalculados em
Python; as duas colunas de receita são indispensáveis.

Uma exportação que ainda preserve todas as posições com nomes distintos, por
exemplo `R$`, `R$_1`, `R$_2` e `R$_3`, pode ser mapeada pelo código usando os
textos da linha amarela. Isso é útil na conferência offline, mas não recupera
o payload ao vivo que já chegou com uma única chave `R$`; o ajuste seguro
continua sendo definir aliases efetivos e únicos no Flexvision.

### 084837: insumos brutos e total positivo do FUNDEB

A 084837 é a cópia operacional criada depois de tornar visível o nó
`FUNDEB-FILTRO`. A 084836 havia sido copiada antes dessa alteração e preservou
a definição antiga no cache da API; a 084834, por sua vez, já havia substituído
a antiga 084805. A consulta atual deve manter somente os dados brutos descritos
abaixo.

A consulta deve fornecer os insumos brutos:

- RP cancelados e excesso aplicado, identificados por exercício, para C;
- RP cancelados do TAC, identificados por exercício, para D; e
- as linhas brutas necessárias aos redutores A e B.

O Python recompõe os agregados, portanto a linha calculada `(I) - (II)` não é
necessária. O corpo seguro de um HTTP 500 da antiga 084805 mostrou falha ao avaliar a
expressão `SE(...)` da linha consolidada B. Remova também essa expressão e
deixe no retorno somente as duas entradas brutas de B; o Python aplica a regra
dos 10%.

Outra resposta HTTP 500 identificou a expressão consolidada
`Restos a Pagar Cancelados (I) - (II)`. Ela também deve ser excluída da
definição da consulta, e não apenas ocultada na apresentação, porque C e D já
são recompostos a partir dos registros anuais brutos.

Nas respostas auditadas da 084834 e de sua cópia 084836, a API trouxe 46 linhas
e todos os insumos A–D, mas omitiu tanto o total direto quanto o nó
`FUNDEB-FILTRO`, embora o valor consolidado exista no CSV adaptado. Como os
R$ 4,75 bilhões dessa linha integram a aplicação, o pipeline precisa receber a
linha pronta ou seu insumo bruto.

Na 084837, a API passou a retornar 47 linhas, incluindo o nó
`(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO` com valor contábil
negativo nos cinco estágios. O Python aplica `0 - filtro` antes de somá-lo aos
valores positivos.

O contrato foi simplificado: o Python procura esse nome exato em qualquer
posição, inverte o valor de cada estágio e substitui o filtro pela linha positiva
no cálculo. Não existem caminhos alternativos para linha pronta ou outro nome.

O pipeline rejeita explicitamente a Parte 2 quando essa linha não chega. Isso
impede que um retorno parcial produza silenciosamente um total liquidado de
aproximadamente R$ 1,29 bilhão no lugar dos R$ 6,04 bilhões reconciliados.
Falhas HTTP 500, 502, 503 e 504 são repetidas no máximo três vezes, com espera
curta e crescente. Se persistirem, o erro seguro informa o ID exato da consulta
sem expor URL, credenciais, token ou corpo integral da resposta.

## Validações e diagnóstico

O pipeline falha de forma explícita quando, entre outros casos:

- falta uma coluna ou linha obrigatória;
- existem cabeçalhos ambíguos ou linhas duplicadas para o mesmo insumo;
- uma linha redutora da Parte 1 chega com sinal positivo;
- um total informado diverge do total recomposto;
- o total aplicado fica negativo; ou
- o JSON possui mais de uma lista sem indicação de qual deve ser usada.

As exceções são `ErroSchemaFlexvision` para problemas de forma/identificação e
`ErroRegraNegocio` para inconsistências numéricas ou de regra. Essas mensagens
podem ser apresentadas no Streamlit com `st.error`, sem expor usuário, senha
ou o conteúdo integral da resposta da API.

## Testes

Os testes são offline e não exigem credenciais da API.

Linux/WSL:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```
