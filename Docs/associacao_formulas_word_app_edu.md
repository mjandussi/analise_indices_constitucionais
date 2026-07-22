# Associação das fórmulas do Word com a implementação modular

## Objetivo

Este documento associa as regras descritas em **Ajustes da Consulta do Índice
Constitucional de Educação** à implementação canônica de
[`educacao.py`](../src/indices_constitucionais/educacao.py). O `app_edu.py`
permanece apenas como ponto de entrada dos dashboards.

Documentos de referência:

- [Arquivo Word original](Ajustes%20da%20Consulta%20do%20Indice%20Constitucional%20de%20Educação.docx)
- [Arquivo Word com a fórmula do FUNDEB acrescentada](Ajustes%20da%20Consulta%20do%20Indice%20Constitucional%20de%20Educação%20-%20com%20fórmula%20FUNDEB.docx)

As fórmulas são executadas separadamente para cada estágio financeiro definido
no aplicativo. O Python recebe os insumos brutos da consulta, identifica as
linhas por sua descrição normalizada e recompõe os resultados.

## Visão geral do fluxo

1. A consulta da Parte 2 fornece as linhas contábeis brutas.
2. O Python resolve a linha positiva das receitas transferidas ao FUNDEB.
3. O Python soma as linhas positivas.
4. Os redutores A, B, C e D são recalculados a partir dos insumos brutos.
5. As demais linhas de dedução são somadas, excluindo os antigos agregados A–D.
6. O total aplicado em educação é calculado pela subtração de todos os redutores.

O encadeamento principal está em
[`calcular_parte2()`](../src/indices_constitucionais/educacao.py).

## Total das receitas transferidas ao FUNDEB

### Regra acrescentada ao Word

```text
0
-
(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO
```

Em forma matemática:

```text
Total positivo do FUNDEB = 0 - valor do FUNDEB-FILTRO
```

O nó `FUNDEB-FILTRO` chega da consulta com valor negativo ou igual a zero.
Subtrair um número negativo de zero inverte seu sinal:

```text
0 - (-4.746.950.289,79) = +4.746.950.289,79
```

Portanto, a fórmula produz a linha positiva que deve integrar a soma das
aplicações.

### Implementação Python

A lógica está em
[`_calcular_total_fundeb_do_filtro()`](../src/indices_constitucionais/educacao.py):

1. procura na consulta 084837 a linha cujo nome é exatamente
   `(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB-FILTRO`;
2. calcula `0 - valor` em cada estágio;
3. inclui no cálculo uma única linha positiva
   `(+) TOTAL DAS RECEITAS TRANSFERIDAS AO FUNDEB`.

O pipeline também aceita a linha positiva direta. Quando as duas formas vêm na
consulta, elas precisam reconciliar centavo a centavo.

## Redutor A — superávit anterior não aplicado

### Regra do Word

O cálculo é realizado separadamente para:

- impostos e transferências de impostos; e
- complementação da União.

Para cada grupo:

```text
A_grupo = máximo(superávit financeiro - aplicação do superávit, 0)
A = A_impostos + A_complementação
```

Essa expressão equivale à condição do Word: se a aplicação for maior ou igual
ao superávit, o redutor será zero; caso contrário, será a diferença entre o
superávit e a aplicação.

### Implementação Python

A classificação dos dois grupos está em
[`_grupo_superavit()`](../src/indices_constitucionais/educacao.py). O cálculo está em
[`_calcular_redutor_a()`](../src/indices_constitucionais/educacao.py), especialmente:

- identifica as quatro linhas de entrada;
- exige exatamente um superávit e uma aplicação por grupo;
- calcula `max(superávit - aplicação, ZERO)` e soma os grupos.

## Redutor B — receitas do FUNDEB não utilizadas acima de 10%

### Regra do Word

```text
B1 = receitas recebidas do FUNDEB - despesas custeadas com recursos do FUNDEB
B2 = receitas recebidas do FUNDEB × 0,10
B  = máximo(B1 - B2, 0)
```

De forma direta:

```text
B = máximo(receita - despesa - receita × 0,10, 0)
```

O limite de 10% não é calculado sobre a linha positiva das receitas
transferidas ao FUNDEB. Ele usa especificamente a linha `RECEITAS RECEBIDAS DO
FUNDEB` identificada como insumo do redutor B.

### Implementação Python

A regra está em
[`_calcular_redutor_b()`](../src/indices_constitucionais/educacao.py):

- localiza a receita recebida e a despesa custeada;
- calcula B1 e o limite B2 para a memória de cálculo;
- calcula diretamente o redutor B, limitado ao mínimo zero.

## Redutor C — Restos a Pagar Cancelados da MDE

### Regra do Word

O cálculo é feito separadamente para cada ano:

```text
C_ano = máximo(RP cancelado do ano - excesso aplicado do ano, 0)
C = soma dos resultados de todos os anos
```

Assim, quando o RP cancelado não supera o excesso já aplicado, o resultado
daquele ano é zero.

### Implementação Python

A regra está em
[`_calcular_redutor_c()`](../src/indices_constitucionais/educacao.py):

- separa por ano os RPs cancelados e os excessos aplicados,
  excluindo as linhas do TAC;
- calcula `max(RP - excesso, ZERO)` para cada ano;
- soma os resultados anuais e guarda a memória detalhada.

## Redutor D — Restos a Pagar Cancelados do TAC

### Regra do Word

```text
D = soma dos RPs cancelados vinculados ao TAC
```

TAC significa Termo de Ajustamento de Conduta.

### Implementação Python

A regra está em
[`_calcular_redutor_d()`](../src/indices_constitucionais/educacao.py):

- seleciona somente linhas `RP CANCELADO TAC` que possuam ano;
- exige os insumos e realiza o somatório;
- conserva os valores por ano para exibição da memória.

## Associação C + D

O Word determina que C e D sejam somados e que o resultado final seja um
redutor. No Python, isso significa que ambos são subtraídos do total aplicado:

```text
Redutor de RPs cancelados = C + D
```

Na fórmula financeira principal, a implementação subtrai `C` e `D`
separadamente, o que é matematicamente equivalente a subtrair `C + D`. Essa
decisão está documentada em
[`calcular_parte2()`](../src/indices_constitucionais/educacao.py).

Para reproduzir a apresentação do relatório antigo, o aplicativo também cria
uma linha visual consolidada `C + D` em
[`relatorio_calculado()`](../app_educacao/apresentacao.py). As linhas individuais C e
D mostradas abaixo dela são apenas memória informativa e não são somadas outra
vez.

## Proteção contra cálculos duplicados

Como A, B, C e D são recompostos em Python, as antigas linhas consolidadas da
consulta não podem entrar novamente como deduções. A função
[`_eh_agregado_abcd()`](../src/indices_constitucionais/educacao.py) reconhece esses
agregados, e `calcular_parte2()` os exclui das outras deduções.

Para o FUNDEB-FILTRO, a linha negativa é substituída pela versão positiva
antes da soma. Assim, existe apenas uma linha desse valor no cálculo.

## Fórmula final da aplicação em educação

Depois de preparar a linha positiva do FUNDEB e calcular os redutores, o total
é obtido por:

```text
Total aplicado = valores positivos
               - A
               - B
               - C
               - D
               - outras deduções
```

O cálculo numérico está em
[`calcular_parte2()`](../src/indices_constitucionais/educacao.py). A mesma composição é exibida ao
usuário por [`quadro_formacao_aplicacao()`](../app_educacao/apresentacao.py) e
[`formula_monetaria()`](../app_educacao/apresentacao.py).

## Resumo da correspondência

| Regra do Word | Fórmula executada em Python | Função principal |
|---|---|---|
| Total positivo do FUNDEB | `0 - FUNDEB-FILTRO` | `_calcular_total_fundeb_do_filtro()` |
| Redutor A | `Σ max(superávit - aplicação, 0)` | `_calcular_redutor_a()` |
| Redutor B | `max(receita - despesa - receita × 10%, 0)` | `_calcular_redutor_b()` |
| Redutor C | `Σ por ano max(RP cancelado - excesso aplicado, 0)` | `_calcular_redutor_c()` |
| Redutor D | `Σ RP cancelado TAC por ano` | `_calcular_redutor_d()` |
| C + D | ambos são redutores e são subtraídos | `calcular_parte2()` |
| Total aplicado | positivos `- A - B - C - D - outras deduções` | `calcular_parte2()` |

## Contrato operacional

A consulta 084837 deve conter a linha positiva do total transferido ao FUNDEB
ou a linha técnica `FUNDEB-FILTRO`. A posição pode mudar; a identificação é
feita pelo texto normalizado e duplicidades são rejeitadas.
