import os
from dotenv import load_dotenv
from siaferio import SiafeAPI, resultado_para_dataframe

load_dotenv()

usuario = os.getenv("SIAFE_USUARIO")
senha = os.getenv("SIAFE_SENHA")

if not usuario or not senha:
    raise RuntimeError(
        "Defina SIAFE_USUARIO e SIAFE_SENHA no arquivo .env."
    )

with SiafeAPI(usuario=usuario, senha=senha) as api:
    dados = api.flexvision.consultar(
        "079653",
        parametros=[2026, 7],
        timeout=300,
    )

df = resultado_para_dataframe(dados)
print(df.head())
print(f"Total de registros: {len(df)}")