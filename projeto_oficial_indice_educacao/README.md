# Índice Constitucional da Educação

Esta pasta é um projeto independente. Copie **o conteúdo dela** para a raiz do
repositório oficial `indice-constitucional-educacao`.

O fluxo implementado é:

```text
extracao.py (define as consultas de educação)
        ↓
extracao_flex.py (autentica e consulta a API)
        ↓
Flexvision (JSON)
        ↓
parte1.csv + parte2.csv
        ↓
dados.py + regras/
        ↓
dash_indice.py ou dash_projecao.py
```

Os cálculos não consomem os arquivos JSON nem consultas antigas. Eles sempre
leem o par de CSVs produzido pela extração atual. Os JSONs permanecem no
mesmo diretório apenas como cópia do retorno original da API.

## Estrutura

```text
.
├── extracao_flex.py     # arquivo único e reutilizável: API, JSON e CSV
├── extracao.py          # configura as duas consultas de educação
├── dados.py             # leitura dos CSVs e métricas
├── dash_indice.py       # índice da educação 
├── dash_projecao.py     # projeção anual para o índice
├── config.py            # IDs, meta, estágios e caminhos
├── regras/              # fórmulas financeiras isoladas
├── docs/                # documento contábil e explicação das regras
├── tests/               # testes offline
├── .env.exemplo
├── .gitignore
└── requirements.txt
```

`extracao_flex.py` usa somente a biblioteca padrão do Python. Ele não depende
do pacote `siaferio`, de `requests`, de `pandas` nem de `python-dotenv`.

## Instalação

Requer Python 3.10 ou mais recente.

No PowerShell, dentro do novo repositório:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copie `.env.exemplo` para `.env` e preencha as credenciais:

```env
SIAFE_USUARIO=seu_usuario
SIAFE_SENHA=sua_senha
```

O `.env` e os dados extraídos não são versionados.

## Uso

### 1. Extrair os dados

```powershell
python .\extracao.py 2026 4
```

As consultas `084835` e `084837` usam o mesmo exercício, período e token de
autenticação. A extração cria uma pasta como:

```text
dados_extraidos/2026/04/
├── parte1.json
├── parte1.csv
├── parte2.json
└── parte2.csv
```

Uma nova extração do mesmo ano e período substitui esses quatro arquivos.

Os CSVs usam `;` e UTF-8 com BOM, para poderem ser abertos diretamente no
Excel sem alterar os valores financeiros.

As consultas `079651`, `079652` e `079653` são as referências oficiais-base.
O ETL executa as cópias operacionais `084835` e `084837`, ajustadas para a API.

### Usar somente o arquivo `extracao_flex.py` em outro projeto

Copie `extracao_flex.py` e coloque um `.env` ao lado dele. Nenhuma instalação
é necessária para executar a extração.

Uma consulta:

```powershell
python .\extracao_flex.py -c relatorio=042612 -p 2026 7
```

Duas ou mais consultas com os mesmos parâmetros:

```powershell
python .\extracao_flex.py `
  -c receitas=084835 `
  -c despesas=084837 `
  -p 2026 4
```

O nome à esquerda de `=` será usado nos arquivos finais. O exemplo acima gera:

```text
dados_flexvision/
├── receitas.json
├── receitas.csv
├── despesas.json
└── despesas.csv
```

Para usar parâmetros diferentes em cada consulta, importe a função e escreva
uma lista simples:

```python
from extracao_flex import extrair_consultas

consultas = [
    {"nome": "primeira", "consulta_id": "042612", "parametros": [2026, 7]},
    {"nome": "segunda", "consulta_id": "084614", "parametros": []},
]

arquivos_csv = extrair_consultas(consultas)
print(arquivos_csv)
```

O CSV final pode ser aberto normalmente pelo pandas:

```python
import pandas as pd

df = pd.read_csv("dados_flexvision/primeira.csv", sep=";", encoding="utf-8-sig")
print(df.head())
```

### 2. Validar pelo terminal

Informe a pasta exata mostrada ao fim da extração:

```powershell
python .\dados.py .\dados_extraidos\2026\04
```

### 3. Abrir os dashboards

Índice atual:

```powershell
streamlit run .\dash_indice.py
```

Projeção anual:

```powershell
streamlit run .\dash_projecao.py
```

O dashboard de projeção usa os CSVs já existentes e não chama novamente a
API. O dashboard do índice só chama a API quando o botão de atualização é
pressionado.

No `dash_indice.py`, os dois relógios têm bases diferentes:

- **Índice do período:** aplicação do estágio selecionado ÷ receita arrecadada.
- **Índice sobre a previsão anual:** despesa liquidada acumulada ÷ receita anual
  prevista.

O segundo relógio é um acompanhamento do realizado diante da previsão anual.
Ele não estima despesas dos meses futuros; essa estimativa pertence ao
`dash_projecao.py`.

## Regras de negócio

O cálculo foi organizado para seguir a mesma lógica de uma planilha:

1. `dados.py` abre os CSVs com pandas e dá nomes curtos às colunas;
2. a Parte 1 fornece diretamente a base e o mínimo de 25%;
3. `regras/calculos.py` transforma a Parte 2 adaptada numa tabela equivalente
   à consulta original no leiaute lógico e nas fórmulas;
4. o total é a soma das linhas `(+)` menos a soma das linhas `(-)`;
5. o índice é a despesa aplicada dividida pela base arrecadada.

Leia a explicação completa em
[`docs/regras_negocio.md`](docs/regras_negocio.md) e confira o documento de
origem em
[`docs/Ajustes da Consulta do Indice Constitucional de Educação - com fórmula FUNDEB.docx`](docs/Ajustes%20da%20Consulta%20do%20Indice%20Constitucional%20de%20Educação%20-%20com%20fórmula%20FUNDEB.docx).

## Testes

Os testes não precisam de credenciais nem fazem chamadas externas:

```powershell
python -m unittest discover -s tests -v
```

Eles verificam que:

- uma autenticação atende uma, duas ou mais consultas;
- o extrator funciona sem pacotes externos;
- o JSON é convertido para os dois CSVs;
- a ETL continua funcionando quando as cópias JSON são inutilizadas;
- FUNDEB e redutores A–D são comprovados com valores diferentes de zero;
- a Parte 2 calculada reproduz o leiaute lógico, soma as linhas positivas e
  subtrai as negativas sem duplicá-las;
- a amostra real de abril de 2026 continua produzindo os valores conferidos;
- a projeção mantém precisão com `Decimal`;
- a pasta copiada não importa código do repositório de origem.

## Onde fazer cada manutenção

- Mudou a URL, autenticação ou conversão genérica para CSV: `extracao_flex.py`.
- Mudou o fluxo específico das duas consultas de educação: `extracao.py`.
- Mudou ID, caminho ou constante: `config.py`.
- Mudou o formato do CSV entregue à análise: `dados.py`.
- Mudou uma fórmula financeira: `regras/calculos.py`,
  `docs/regras_negocio.md` e `tests/test_regras.py`.
- Mudou somente a tela: um dos dois arquivos `dash_*.py`.

Essa separação mantém a integração, as regras e a apresentação independentes,
sem duplicar os cálculos entre os dois dashboards.
