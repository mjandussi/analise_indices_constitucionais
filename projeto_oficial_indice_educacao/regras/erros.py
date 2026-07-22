"""Exceções de domínio com mensagens próprias para diagnóstico da carga."""


class ErroDadosFlexvision(ValueError):
    """Erro base para respostas Flexvision que não podem ser processadas."""


class ErroSchemaFlexvision(ErroDadosFlexvision):
    """O retorno não possui as colunas ou linhas necessárias."""


class ErroRegraNegocio(ErroDadosFlexvision):
    """Os dados violam uma premissa necessária ao cálculo."""
