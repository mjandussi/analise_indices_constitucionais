# Monitor indicativo da meta anual de Educação

## Finalidade

O monitor é uma camada opcional, separada do cálculo oficial do índice. Ele
fica fechado por padrão e aparece quando o usuário marca **Ativar monitor
anual**.

Esta versão não é uma previsão estatística. Para a MDE com impostos, ela
prolonga até dezembro o ritmo médio mensal observado no próprio exercício. Para
o FUNDEB, utiliza a previsão anual já calculada na Parte 1.

## Componentes projetados

O numerador é separado em dois componentes principais:

1. MDE com recursos de impostos;
2. transferências concedidas ao FUNDEB.

Os redutores A–D já apurados permanecem no valor atual. O monitor não estima
novos redutores para os meses futuros.

### MDE com recursos de impostos

O valor acumulado é recomposto diretamente da Parte 2:

```text
MDE/impostos acumulada
= valores positivos
- transferência ao FUNDEB
- outras deduções ordinárias
```

No exemplo homologado de abril de 2026, o resultado é
R$ 1.348.782.753,27, igual à linha 19 do RREO.

### Transferências ao FUNDEB

Quando a Parte 1 contém a linha `TOTAL DESTINADO AO FUNDEB`, o app lê:

- o FUNDEB realizado até o período;
- a previsão anual atualizada do FUNDEB.

O valor realizado é reconciliado com a linha positiva calculada pela Parte 2 a
partir do `FUNDEB-FILTRO`. Uma divergência interrompe a simulação para evitar
dupla contagem ou uso de valores incompatíveis.

Se a Parte 1 não trouxer a previsão anual dessa linha, o monitor não é
interrompido. Ele estima automaticamente o total anual pelo ritmo médio do
FUNDEB realizado e apresenta um aviso explícito. O realizado pode vir da Parte
2 quando não estiver disponível na Parte 1.

A previsão atualizada da Parte 1, quando disponível, tem preferência sobre a
estimativa pela média.

## Projeção da MDE pelo ritmo mensal

Para a MDE com impostos, exceto FUNDEB:

```text
Média mensal MDE = MDE/impostos acumulada ÷ número do período
```

```text
MDE futura estimada = média mensal MDE × meses restantes
```

## Saldo anual do FUNDEB

Quando a previsão anual está disponível, o valor futuro do FUNDEB não é
calculado por média:

```text
Saldo FUNDEB até dezembro
= previsão anual atualizada da Parte 1 - FUNDEB já realizado
```

Quando a consulta não contém essa previsão anual, aplica-se o fallback:

```text
FUNDEB anual estimado = FUNDEB realizado ÷ número do período × 12
```

```text
Saldo FUNDEB até dezembro = FUNDEB anual estimado - FUNDEB realizado
```

Sem reajuste, a estimativa de dezembro é:

```text
Aplicação projetada
= aplicação liquidada atual
+ MDE futura estimada
+ saldo anual previsto do FUNDEB
```

Essa construção preserva os redutores já descontados na aplicação atual e não
soma novamente os valores acumulados de MDE e FUNDEB.

## Reajuste percentual opcional

O usuário não informa uma base monetária. Ele escolhe somente:

- o percentual do reajuste; e
- o mês futuro em que o reajuste começa.

A base é calculada automaticamente somente pela média mensal das despesas com
ações típicas de MDE custeadas com receitas de impostos, exceto FUNDEB:

```text
Base automática do reajuste
= média mensal MDE × quantidade de meses futuros atingidos
```

```text
Acréscimo simplificado
= base automática × percentual escolhido
```

```text
Aplicação projetada com reajuste
= aplicação projetada sem reajuste + acréscimo simplificado
```

O percentual sugerido inicialmente é 11,56%, mas pode ser alterado. Essa é uma
aproximação gerencial sobre a MDE com impostos: não representa cálculo de folha
nem afirma que toda essa MDE seja despesa de pessoal. O percentual não incide
sobre as transferências ao FUNDEB.

## Meta e resultado

```text
Meta monetária = base constitucional anual × percentual da meta
```

O painel compara a aplicação projetada com essa meta e mostra:

- aplicação indicativa em dezembro;
- índice indicativo projetado;
- margem positiva ou insuficiência em relação à meta;
- memória dos valores acumulados, médias e parcelas futuras.

A situação é classificada assim:

- **Confortável**: a projeção alcança a meta escolhida;
- **Atenção**: alcança 25%, mas não uma meta gerencial superior;
- **Risco**: não alcança o mínimo de 25%.

## Premissas e limitações

- O número do período deve corresponder aos meses efetivamente acumulados pela
  consulta. Se a fonte representar apenas bimestres fechados, deve-se usar o
  último mês coberto pelo bimestre.
- O ritmo mensal desconsidera sazonalidade da receita e da despesa.
- A MDE pode não manter até dezembro o mesmo comportamento médio.
- O FUNDEB anual segue a previsão da Parte 1 quando disponível; caso contrário,
  utiliza a média mensal realizada com aviso na tela.
- Novos redutores, cancelamentos ou ajustes contábeis não são projetados.
- O reajuste nunca é aplicado ao FUNDEB.
- Não há consultas retroativas, backtest ou cruzamento com SIGA e SIGRH.

O resultado é um instrumento indicativo para acompanhamento e discussão, não
uma previsão contábil homologada para o encerramento do exercício.

## Evolução futura

Se for necessária maior acurácia, uma etapa posterior poderá incorporar:

- composição de pessoal por órgão, UG e rubrica no SIGRH;
- contratos e licitações do SIGA;
- cronogramas de desembolso;
- sazonalidade e previsão de novos redutores.
