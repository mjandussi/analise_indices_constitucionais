# Instalar a biblioteca
python -m pip install -e "..\client_api_siaferio[all]"  

# Ver a versão deste client instalado
python -c "import siaferio; print(siaferio.__version__); print(siaferio.__file__)"  

# Verificar se foi instalado corretamente
python -c "from siaferio import SiafeAPI, resultado_para_dataframe; print('Client carregado corretamente')"                                                    