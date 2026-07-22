# Aplicação modular de educação

Esta pasta separa o antigo `app_edu.py` pelo fluxo dos dados. Cada arquivo tem
uma responsabilidade principal:

| Arquivo | Responsabilidade |
|---|---|
| `extracao.py` | Consultar 084835/084837 e publicar `parte1.csv` + `parte2.csv` |
| `dados.py` | Ler os dois CSVs, executar a ETL e produzir métricas |
| `dash_indice.py` | Exibir o índice atual, gráficos e memória de cálculo |
| `dash_projecao.py` | Exibir somente o monitor/projeção anual |
| `graficos.py` | Componentes visuais reutilizados pelo dashboard do índice |
| `memoria.py` | Tabelas de auditoria e abertura dos redutores A–D |
| `apresentacao.py` | Formatação de linhas e mensagens seguras |
| `config.py` | IDs, estágios e constantes da aplicação |

As fórmulas financeiras continuam centralizadas em
`src/indices_constitucionais`. Assim, `dados.py` coordena a ETL sem manter uma
segunda cópia dos cálculos A–D.

## Fluxo

```text
Client SIAFE/Flexvision
  ├─ consulta 084835 ──> JSON ──> parte1.csv ──┐
  └─ consulta 084837 ──> JSON ──> parte2.csv ──┤
                                                └─> dados.py
                                                      ├─> índice atual
                                                      └─> projeção anual
```

Os dois CSVs são publicados juntos. Uma pasta temporária é preparada primeiro
e só vira um snapshot visível depois que todos os arquivos e metadados foram
gravados. Isso impede que a ETL combine uma Parte 1 nova com uma Parte 2 antiga.

## Executar

```powershell
# Apenas extração
python -m app_educacao.extracao 2026 4

# Dashboard do índice atual
python -m streamlit run app_educacao/dash_indice.py

# Dashboard da projeção
python -m streamlit run app_educacao/dash_projecao.py

# Página histórica com as duas áreas
python -m streamlit run app_edu.py
```

## Trocar o client no futuro

A dependência do client está limitada a `extrair_dados_educacao()`. Hoje a
função cria `siaferio.SiafeAPI`; para testar ou integrar outro client, é
possível informar `fabrica_api=` e `credenciais=`. O objeto fornecido precisa
ser um gerenciador de contexto e expor `api.flexvision.consultar(...)`.

Se o client padrão do setor tiver outra interface, crie um adaptador pequeno
nesse mesmo arquivo. Nenhuma alteração será necessária em `dados.py` ou nos
dashboards, porque o contrato entre as camadas são os dois CSVs.
