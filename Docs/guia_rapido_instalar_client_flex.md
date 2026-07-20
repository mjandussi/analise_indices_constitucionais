# Guia rápido: usar o client em outro repositório local

Este guia mostra como usar o `siaferio-client` em outro projeto no mesmo
notebook, sem copiar a pasta `siaferio` para o projeto consumidor.

## Estrutura sugerida

Mantenha os dois repositórios como pastas vizinhas:

```text
D:\GitHub\
├── client_api_siaferio\
└── meu_projeto\
```

O nome instalado pelo `pip` é `siaferio-client`, mas o nome usado no
`import` é `siaferio`.

## 1. Crie o ambiente virtual do outro projeto

Abra o PowerShell na pasta do projeto consumidor:

```powershell
cd D:\GitHub\meu_projeto
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Cada projeto deve possuir seu próprio ambiente virtual. Não reutilize o
`venv` existente dentro de `client_api_siaferio`.

## 2. Instale o client local em modo editável

Se os repositórios forem pastas vizinhas, execute:

```powershell
python -m pip install -e "..\client_api_siaferio[all]"
```

Também é possível informar o caminho completo:

```powershell
python -m pip install -e "D:\GitHub\client_api_siaferio[all]"
```

O modo editável (`-e`) faz o projeto consumidor utilizar diretamente o código
da pasta `client_api_siaferio`. Alterações feitas no client ficam disponíveis
sem copiar arquivos ou reinstalar o pacote.

O extra `[all]` inclui suporte a `.env`, pandas e Excel. Para usar somente o
JSON retornado pela API, ele pode ser omitido.

## 3. Confirme a instalação

Ainda no ambiente virtual do projeto consumidor:

```powershell
python -c "import siaferio; print(siaferio.__version__); print(siaferio.__file__)"
python -m pip show siaferio-client
```

O caminho exibido por `siaferio.__file__` deve apontar para:

```text
D:\GitHub\client_api_siaferio\siaferio\__init__.py
```

## 4. Configure as credenciais no projeto consumidor

Crie `D:\GitHub\meu_projeto\.env`:

```env
SIAFE_USUARIO=seu_cpf_sem_pontuacao
SIAFE_SENHA=sua_senha
```

Adicione ao `.gitignore` do projeto consumidor:

```gitignore
.env
.venv/
outputs/
```

Nunca copie ou versione credenciais dentro do código, do `requirements.txt`
ou do repositório do client.

## 5. Faça uma consulta mínima

Crie `consultar_siafe.py` no projeto consumidor:

```python
import os

from dotenv import load_dotenv
from siaferio import SiafeAPI, resultado_para_dataframe


load_dotenv()

usuario = os.getenv("SIAFE_USUARIO")
senha = os.getenv("SIAFE_SENHA")

if not usuario or not senha:
    raise RuntimeError("Defina SIAFE_USUARIO e SIAFE_SENHA no arquivo .env.")

with SiafeAPI(usuario=usuario, senha=senha) as api:
    resultado = api.flexvision.consultar(
        "042612",
        parametros=[2026, 7],
        timeout=300,
    )

df = resultado_para_dataframe(resultado)
print(df.head())
print(f"Total de registros: {len(df)}")
```

Execute a partir da raiz do projeto consumidor:

```powershell
python .\consultar_siafe.py
```

Substitua o ID e os parâmetros pelos valores da consulta Flexvision que você
tem permissão para acessar.

## 6. Registre a dependência local

Durante o desenvolvimento no mesmo notebook, o `requirements.txt` do projeto
consumidor pode conter:

```text
-e ../client_api_siaferio[all]
```

Assim, o ambiente poderá ser recriado com:

```powershell
python -m pip install -r requirements.txt
```

Esse caminho relativo só funciona enquanto os repositórios continuarem
vizinhos. Para compartilhar o projeto com outras pessoas, prefira instalar o
client por uma tag fixa do Git, conforme descrito em
[Compartilhamento e distribuição](compartilhamento.md).

## Problemas comuns

### `ModuleNotFoundError: No module named 'siaferio'`

O client não foi instalado no ambiente que executou o programa. Confira:

```powershell
python -c "import sys; print(sys.executable)"
python -m pip show siaferio-client
```

Reinstale usando o mesmo `python`:

```powershell
python -m pip install -e "..\client_api_siaferio[all]"
```

### O terminal funciona, mas o VS Code marca o import como ausente

No VS Code, execute **Python: Select Interpreter** e selecione:

```text
D:\GitHub\meu_projeto\.venv\Scripts\python.exe
```

### Alterei o `.env`, mas o programa ainda usa um valor antigo

Por padrão, `load_dotenv()` não substitui uma variável já definida no Windows
ou no terminal. Feche e reabra o terminal ou, quando essa substituição for
intencional, use:

```python
load_dotenv(override=True)
```

### `HTTP 401` informando envio de código por e-mail

Esse retorno indica uma segunda etapa de autenticação exigida pelo SIAFE-Rio.
O client atual ainda não possui um fluxo documentado para fornecer esse
código. Verifique o e-mail cadastrado e procure a SUGESC se a API continuar
exigindo o código mesmo com o acesso normal ao portal funcionando.

### A pasta do client foi movida

A instalação editável guarda uma referência à pasta original. Reinstale usando
o caminho novo:

```powershell
python -m pip uninstall siaferio-client
python -m pip install -e "NOVO_CAMINHO\client_api_siaferio[all]"
```
