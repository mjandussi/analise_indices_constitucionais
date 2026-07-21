"""Exceções de domínio com mensagens próprias para diagnóstico da carga."""


class ErroDadosFlexvision(ValueError):
    """Erro base para respostas Flexvision que não podem ser processadas."""


class ErroSchemaFlexvision(ErroDadosFlexvision):
    """O retorno não possui as colunas ou linhas necessárias."""


class ErroRegraNegocio(ErroDadosFlexvision):
    """Os dados violam uma premissa necessária ao cálculo."""


class ErroConsultaFlexvision(RuntimeError):
    """Uma consulta identificada falhou no servidor após as tentativas permitidas."""

    def __init__(self, consulta_id: str, original: Exception, tentativas: int) -> None:
        self.consulta_id = str(consulta_id)
        self.original = original
        self.tentativas = int(tentativas)
        self.response = getattr(original, "response", None)
        super().__init__(
            f"A consulta {self.consulta_id} falhou após {self.tentativas} "
            "tentativa(s)."
        )
