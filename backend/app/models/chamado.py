"""
Modelos SQLAlchemy do banco novo (helpdesk).

Observação sobre usuario_codigo / responsavel_codigo / criado_por_codigo:
esses campos referenciam usuários que vivem no banco LEGADO (telemedicina),
não neste banco. Por isso não são ForeignKey de verdade (PostgreSQL não
permite FK entre bancos de dados diferentes) — guardamos o código e um
snapshot do nome no momento da ação, seguindo o mesmo princípio já usado
para cliente_codigo.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.helpdesk_db import Base


class Status(Base):
    __tablename__ = "status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cor: Mapped[str] = mapped_column(String(7), nullable=False, default="#6b7280")
    finalizador: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Prioridade(Base):
    __tablename__ = "prioridade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cor: Mapped[str] = mapped_column(String(7), nullable=False, default="#6b7280")
    sla_horas: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Categoria(Base):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Chamado(Base):
    __tablename__ = "chamado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero_chamado: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)

    # Referência ao cliente na base legada (não-FK, banco diferente)
    cliente_codigo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cliente_nome_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    cliente_contato_snapshot: Mapped[str | None] = mapped_column(String(255))
    cliente_telefone_snapshot: Mapped[str | None] = mapped_column(String(50))

    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)

    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), nullable=False)
    prioridade_id: Mapped[int] = mapped_column(ForeignKey("prioridade.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("status.id"), nullable=False)

    # Referências a usuários da base legada (não-FK, banco diferente)
    responsavel_codigo: Mapped[int | None] = mapped_column(Integer, index=True)
    responsavel_nome_snapshot: Mapped[str | None] = mapped_column(String(255))
    criado_por_codigo: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    criado_por_nome_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    encerrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    excluido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excluido_por_codigo: Mapped[int | None] = mapped_column(Integer)
    excluido_por_nome_snapshot: Mapped[str | None] = mapped_column(String(255))

     # Guarda o último estado de SLA já notificado ("proximo"/"estourado"),
    # para o monitor periódico não avisar o mesmo alerta repetidas vezes.
    sla_notificado_status: Mapped[str | None] = mapped_column(String(20))
    
    prazo_sla: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    categoria: Mapped["Categoria"] = relationship()
    prioridade: Mapped["Prioridade"] = relationship()
    status: Mapped["Status"] = relationship()
    historico: Mapped[list["ChamadoHistorico"]] = relationship(
        back_populates="chamado", order_by="ChamadoHistorico.criado_em"
    )
    interacoes: Mapped[list["ChamadoInteracao"]] = relationship(
        back_populates="chamado", order_by="ChamadoInteracao.criado_em"
    )
    anexos: Mapped[list["ChamadoAnexo"]] = relationship(
        back_populates="chamado", order_by="ChamadoAnexo.criado_em"
    )

class ChamadoContadorDiario(Base):
    """
    Contador auxiliar usado para gerar o número sequencial diário do
    chamado (formato DDMMAA + sequência). Uma linha por dia.
    """
    __tablename__ = "chamado_contador_diario"

    data: Mapped[date] = mapped_column(Date, primary_key=True)
    contador: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class ChamadoHistorico(Base):
    """
    Trilha de auditoria do chamado: quem fez, o que fez, quando,
    valor anterior e valor novo.
    """
    __tablename__ = "chamado_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamado.id"), nullable=False, index=True)

    usuario_codigo: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_nome_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)

    campo_alterado: Mapped[str] = mapped_column(String(50), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_novo: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chamado: Mapped["Chamado"] = relationship(back_populates="historico")


class ChamadoInteracao(Base):
    """Comentários e andamentos registrados durante o atendimento."""
    __tablename__ = "chamado_interacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamado.id"), nullable=False, index=True)

    usuario_codigo: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_nome_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)

    texto: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chamado: Mapped["Chamado"] = relationship(back_populates="interacoes")

class ChamadoAnexo(Base):
    """
    Metadados dos arquivos anexados ao chamado. O arquivo físico fica em
    disco, em settings.anexos_dir; aqui guardamos apenas a referência.
    """
    __tablename__ = "chamado_anexo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamado.id"), nullable=False, index=True)

    nome_original: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_armazenado: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    enviado_por_codigo: Mapped[int] = mapped_column(Integer, nullable=False)
    enviado_por_nome_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chamado: Mapped["Chamado"] = relationship(back_populates="anexos")

class UsuarioContato(Base):
    """
    Número de WhatsApp de cada usuário do Help Desk, usado para
    notificações individuais (ex: "você foi atribuído a um chamado").
    O usuário em si vive no banco legado; aqui só guardamos a referência.
    """
    __tablename__ = "usuario_contato"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_codigo: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    usuario_nome_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    whatsapp_numero: Mapped[str | None] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )