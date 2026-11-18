"""Modelo de auditoria central das interações do Help Desk."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.helpdesk_db import Base


class AuditoriaLog(Base):
    __tablename__ = "auditoria_log"
    __table_args__ = (
        Index("ix_auditoria_log_categoria_criado_em", "categoria", "criado_em"),
        Index("ix_auditoria_log_tipo_criado_em", "tipo_evento", "criado_em"),
        Index("ix_auditoria_log_resultado_criado_em", "resultado", "criado_em"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_codigo: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    usuario_login: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    usuario_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tipo_evento: Mapped[str] = mapped_column(String(20), nullable=False)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)
    acao: Mapped[str] = mapped_column(String(120), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)

    metodo_http: Mapped[str | None] = mapped_column(String(10), nullable=True)
    caminho: Mapped[str | None] = mapped_column(String(500), nullable=True)
    entidade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entidade_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status_http: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ip_origem: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detalhes: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
