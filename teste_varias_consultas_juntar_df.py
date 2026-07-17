import os
from dotenv import load_dotenv
from siaferio import SiafeAPI, resultado_para_dataframe
import pandas as pd

load_dotenv()

usuario = os.getenv("SIAFE_USUARIO")
senha = os.getenv("SIAFE_SENHA")

if not usuario or not senha:
    raise RuntimeError(
        "Defina SIAFE_USUARIO e SIAFE_SENHA no arquivo .env."
    )
consultas = [
    {
        "id": "049181",
        "parametros": [2026, 4],
        "timeout": 300,
    },
    {
        "id": "084771",
        "parametros": [2026, 5],
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


###################################################
## JUNTAR DFs ##

df_unificado = pd.concat(
    [
        df.assign(_consulta_id=consulta_id)
        for consulta_id, df in dfs.items()
    ],
    ignore_index=True,
    sort=False,
)

colunas_iguais = (
    set(dfs["049181"].columns)
    == set(dfs["084771"].columns)
)

print(f"As consultas possuem as mesmas colunas? {colunas_iguais}")
print(df_unificado.head())
print(df_unificado.groupby("_consulta_id").size())
for consulta_id, df in dfs.items():
    print(f"Consulta {consulta_id}: {len(df)} registros e {len(df.columns)} colunas")