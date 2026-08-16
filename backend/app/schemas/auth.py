from pydantic import BaseModel


class LoginRequest(BaseModel):
    login: str
    senha: str


class UsuarioLogado(BaseModel):
    codigo: int
    login: str
    nome: str