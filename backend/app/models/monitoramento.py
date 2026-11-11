"""Modelos de histórico e auditoria do monitoramento de infraestrutura."""
from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.helpdesk_db import Base


class MonitoramentoAmostra(Base):
    __tablename__ = "monitoramento_amostra"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    cpu_percentual: Mapped[float] = mapped_column(Float, nullable=False)
    memoria_percentual: Mapped[float] = mapped_column(Float, nullable=False)
    detalhes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class MonitoramentoAcao(Base):
    __tablename__ = "monitoramento_acao"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_codigo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    usuario_login: Mapped[str] = mapped_column(String(100), nullable=False)
    usuario_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    acionado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    resultado: Mapped[str] = mapped_column(String(30), nullable=False)
    detalhe: Mapped[str | None] = mapped_column(Text)
