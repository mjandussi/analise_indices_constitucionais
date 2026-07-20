import json
import os

from dotenv import load_dotenv
from requests import HTTPError
from siaferio import SiafeAPI, resultado_para_dataframe

load_dotenv()

usuario = os.getenv("SIAFE_USUARIO")
senha = os.getenv("SIAFE_SENHA")

try:
    with SiafeAPI(usuario=usuario, senha=senha) as api:
        dados = api.flexvision.consultar(
            "084805",
            parametros=[2026, 4],
            timeout=300,
        )

except HTTPError as erro:
    resposta = erro.response

    print("\n=== DIAGNÓSTICO DA API ===", flush=True)
    print(f"Erro: {erro}", flush=True)

    if resposta is None:
        print("A exceção não contém uma resposta HTTP.", flush=True)
    else:
        print(f"HTTP: {resposta.status_code}", flush=True)
        print(f"URL: {resposta.url}", flush=True)
        print(
            f"Content-Type: {resposta.headers.get('Content-Type')}",
            flush=True,
        )

        corpo = resposta.text.strip()

        if corpo:
            print(f"\nCorpo da resposta:\n{corpo}", flush=True)
        else:
            print("\nCorpo da resposta: <vazio>", flush=True)

    raise SystemExit(1)


print("\n=== JSON BRUTO DA API ===")
print(f"Tipo: {type(dados).__name__}")
print(
    json.dumps(
        dados,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)

df = resultado_para_dataframe(dados)
print("\n=== DATAFRAME ===")
print(df)

# df = resultado_para_dataframe(dados)
# print(df.head())