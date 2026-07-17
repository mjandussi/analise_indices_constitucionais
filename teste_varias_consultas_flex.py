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
consultas = [
    {
        "id": "079651",
        "parametros": [2026, 7],
        "timeout": 300,
    },
    {
        "id": "079653",
        "parametros": [2026, 7],
        "timeout": 300,
    },
]

with SiafeAPI(usuario=usuario, senha=senha) as api:
    resultados = api.flexvision.consultar_varias(
        consultas,
        max_workers=2,
    )

dfs = {
    consulta_id: resultado_para_dataframe(resultado)
    for consulta_id, resultado in resultados.items()
}

df_079651 = dfs["079651"]
df_079653 = dfs["079653"]

print("Consulta 079651:")
print(df_079651.head())
print(f"Total: {len(df_079651)}")

print("\nConsulta 079653:")
print(df_079653.head())
print(f"Total: {len(df_079653)}")