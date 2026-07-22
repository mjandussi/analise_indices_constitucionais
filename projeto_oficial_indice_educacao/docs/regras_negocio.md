# Regras de negócio — Índice Constitucional da Educação

Este documento explica o cálculo da mesma forma que ele seria conferido no
Excel. O código correspondente está em `regras/calculos.py`.

Documento contábil de origem:
[`Ajustes da Consulta do Indice Constitucional de Educação - com fórmula FUNDEB.docx`](Ajustes%20da%20Consulta%20do%20Indice%20Constitucional%20de%20Educação%20-%20com%20fórmula%20FUNDEB.docx).

## 1. Origem dos dados

```text
Consultas oficiais-base: 079651, 079652 e 079653
                         ↓ cópias e ajustes no Flexvision
Consultas usadas no ETL: 084835 e 084837
                         ↓
                    JSON → CSV → pandas
```

As três consultas `079651`, `079652` e `079653` permanecem como referência
oficial. O ETL não as altera nem as executa.

As duas consultas operacionais são:

| Consulta | Uso no ETL | Ajuste principal |
|---|---|---|
| `084835` | Parte 1 | Remove as duas linhas visuais anteriores ao cabeçalho e entrega nomes de colunas únicos para o JSON. |
| `084837` | Parte 2 | Entrega os dados brutos usados para calcular A, B, C, D e o total do FUNDEB. |

O vínculo individual entre cada uma das três consultas oficiais e as duas
consultas operacionais deve ser registrado quando for formalmente confirmado.
O projeto não presume uma relação individual que não esteja documentada.

## 2. Parte 1 — receita

A Parte 1 adaptada possui os mesmos dados da original. A mudança foi somente
retirar as duas primeiras linhas visuais para que a linha correta se tornasse o
cabeçalho da tabela.

Por isso, o Python apenas lê as linhas prontas:

- `TOTAL - BASE DE CÁLCULO`;
- `VALOR A SER APLICADO EM EDUCAÇÃO (25%)`.

Os cinco cabeçalhos esperados da consulta `084835` são descrição, `Receita
Prevista`, `Receita Arrecadada`, `Diferença (B-A)` e
`Arrecadada/Prevista`.

Para o índice do período, a base é a **Receita Arrecadada**. A coluna
**Receita Prevista** é usada no acompanhamento anual.

## 3. Parte 2 adaptada → Parte 2 calculada

A Parte 2 adaptada não traz todas as linhas consolidadas da original porque as
fórmulas antigas provocavam erro na API. Ela traz os dados brutos. O arquivo
`regras/calculos.py` usa pandas para reconstruir as linhas que faltam, com o
mesmo leiaute lógico e as mesmas fórmulas da consulta original.

A consulta original exibia algumas parcelas arredondadas. O projeto não força
esse arredondamento visual: ele preserva os centavos recebidos da `084837`.
Assim, uma diferença de centavos em relação ao print antigo não representa uma
diferença na regra contábil.

### Total positivo do FUNDEB

Quando a API entrega o `FUNDEB-FILTRO` negativo:

```text
FUNDEB positivo = 0 - FUNDEB-FILTRO
```

Exemplo:

```text
0 - (-4.746.950.289,79) = 4.746.950.289,79
```

Se uma exportação já trouxer diretamente a linha positiva, ela também pode ser
utilizada. O valor entra uma única vez na tabela calculada.

Da mesma forma, se uma exportação híbrida trouxer os dados brutos e também as
antigas linhas consolidadas A, B ou C+D, prevalece o cálculo feito a partir dos
dados brutos. Assim, nenhum redutor entra duas vezes.

### Redutor A — superávit anterior

O cálculo é separado em dois grupos:

```text
A_impostos       = máximo(superávit - aplicação do superávit, 0)
A_complementação = máximo(superávit - aplicação do superávit, 0)
A                = A_impostos + A_complementação
```

### Redutor B — FUNDEB não utilizado acima de 10%

```text
Valor não aplicado = receita recebida - despesa custeada
Limite permitido   = receita recebida × 10%
B                   = máximo(valor não aplicado - limite, 0)
```

Como numa fórmula do Excel, os 10% permanecem com a precisão completa durante
a conta. O redutor final é arredondado para centavos.

### Redutor C — restos a pagar cancelados da MDE

O cálculo é feito separadamente por exercício:

```text
C_ano = máximo(RP cancelado do ano - excesso aplicado do ano, 0)
C     = soma dos resultados de todos os anos
```

Quando um dos dois valores não existe para determinado ano, ele é considerado
zero, da mesma forma que uma célula vazia usada numa subtração da planilha.

### Redutor D — restos a pagar do TAC

```text
D = soma dos RPs cancelados vinculados ao TAC
```

Na consulta adaptada, os prefixos `C` e `D` aparecem invertidos em relação ao
documento da regra. Por isso, o pandas identifica as linhas pelo texto `TAC`,
`RPP`, `RPNP`, `EXCESSO APLICADO` e pelo ano.

### Linha consolidada dos restos a pagar

O documento Word determina que C e D sejam somados como redutores:

```text
Redutor de restos a pagar = C + D
```

A tabela calculada mantém o título visual legado
`Restos a Pagar Cancelados (I) - (II)` para facilitar a comparação com a
consulta original. O valor preenchido nessa linha é `C + D`. As linhas
individuais `(I)` e `(II)` aparecem somente como memória e não entram novamente
na soma.

## 4. Total aplicado — conta igual à do Excel

Depois de reconstruir a Parte 2, o pandas usa somente os sinais escritos no
início das descrições:

```text
Valores positivos = soma das linhas que começam com (+)
Valores negativos = soma das linhas que começam com (-)

Despesa aplicada = valores positivos - valores negativos
```

As linhas brutas A, B, C e D são insumos. Elas não aparecem na tabela final e
não são somadas uma segunda vez.

O mesmo cálculo é executado para:

- dotação atual;
- despesa autorizada;
- despesa empenhada;
- despesa liquidada;
- despesa paga.

O arquivo `regras/calculos.py` usa pandas para filtrar e organizar as linhas.
Os valores financeiros são mantidos como `Decimal`; uma célula financeira
vazia é tratada como zero.

## 5. Índice constitucional

```text
Índice do período =
    despesa aplicada do estágio escolhido
    ÷ receita arrecadada da Parte 1
    × 100
```

O estágio inicialmente apresentado é a despesa liquidada.

O segundo relógio do dashboard é apenas um acompanhamento anual:

```text
Índice sobre a previsão anual =
    despesa liquidada acumulada
    ÷ receita anual prevista
    × 100
```

Ele não projeta despesas futuras.

## 6. Exemplo didático usado no teste

```text
Valores positivos                    1.100,00
(-) A                                   90,00
(-) B                                   30,00
(-) C + D                               75,00
(-) Outras deduções                    25,00
= Despesa aplicada                     880,00
```

Com uma base arrecadada de `800,00`:

```text
Índice = 880 ÷ 800 × 100 = 110%
```

Esse exemplo está em `tests/test_regras.py` e deve ser atualizado sempre que
uma regra contábil for alterada.

## 7. Resultado real conferido — abril de 2026

Os CSVs usados nessa conferência ficam em `tests/fixtures/abril_2026`. O teste
`test_resultado_real_de_abril_de_2026` protege os valores abaixo contra
alterações acidentais no código.

```text
Valores positivos com FUNDEB      6.208.296.729,18
(-) Redutor A                                 0,00
(-) Redutor B                        58.377.935,29
(-) Redutores C + D                           0,00
(-) Outras deduções                 112.563.686,12
= Despesa liquidada aplicada       6.037.355.107,77
```

```text
Base arrecadada                   25.852.525.422,83
Índice liquidado                           23,35%
```

## 8. Onde alterar

- IDs das consultas: `config.py`.
- API e conversão JSON → CSV: `extracao_flex.py`.
- Colunas recebidas e preparação dos DataFrames: `dados.py`.
- Fórmulas A, B, C, D, FUNDEB e soma final: `regras/calculos.py`.
- Apresentação: `dash_indice.py` e `dash_projecao.py`.
- Conferência das regras: `tests/test_regras.py`.
