from pydantic import BaseModel


class NovoChamadoRequest(BaseModel):
    cliente_codigo: int
    titulo: str
    descricao: str
    categoria_ids: list[int]
    prioridade_id: int
    responsavel_codigo: int | None = None