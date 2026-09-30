"""
Geração da Ordem de Serviço (OS) em PDF, no layout do formulário em
papel já usado pela equipe. Gera uma folha A4 com duas vias A5
(paisagem) empilhadas, prontas para impressão e corte.
"""
import os
import textwrap
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.datas import para_horario_local

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "LOGO_TELEMEDICINA.svg")

LARGURA_VIA = 210 * mm   # A5 paisagem
ALTURA_VIA = 148 * mm


def _checkbox(c, x, y, tamanho, marcado=False):
    c.rect(x, y - tamanho, tamanho, tamanho, stroke=1, fill=0)
    if marcado:
        c.setLineWidth(1.3)
        c.line(x + 0.6 * mm, y - tamanho + 0.6 * mm, x + tamanho - 0.6 * mm, y - 0.6 * mm)
        c.line(x + 0.6 * mm, y - 0.6 * mm, x + tamanho - 0.6 * mm, y - tamanho + 0.6 * mm)
        c.setLineWidth(1)


def _linha_com_valor(c, x_ini, y, x_fim, label, valor):
    c.setFont("Helvetica", 9.5)
    c.drawString(x_ini, y, label)
    largura_label = c.stringWidth(label, "Helvetica", 9.5)
    x_valor = x_ini + largura_label + 2 * mm
    c.line(x_valor, y - 1 * mm, x_fim, y - 1 * mm)
    if valor:
        c.setFont("Helvetica", 9.5)
        c.drawString(x_valor + 1.5 * mm, y + 0.5 * mm, valor)


def _desenhar_via(c, y_offset, chamado, numero_os, data_impressao_str, responsavel_nome, categorias_nomes, descricao):
    c.saveState()
    c.translate(0, y_offset)

    margem = 5 * mm
    c.setLineWidth(1)
    c.roundRect(margem, margem, LARGURA_VIA - 2 * margem, ALTURA_VIA - 2 * margem, 4 * mm, stroke=1, fill=0)

    x0 = margem + 4 * mm
    y = ALTURA_VIA - margem - 6 * mm

    # Tipo de visita (em branco, marcado manualmente)
    c.setFont("Helvetica-Bold", 8.5)
    _checkbox(c, x0, y, 3.2 * mm)
    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "VISITA CORRETIVA")
    y -= 6.5 * mm
    _checkbox(c, x0, y, 3.2 * mm)
    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "VISITA PREVENTIVA")

    # Logo
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(
                LOGO_PATH, 76 * mm, ALTURA_VIA - margem - 15 * mm,
                width=40 * mm, height=13 * mm, preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # Título
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(120 * mm, ALTURA_VIA - margem - 7 * mm, "SOLICITAÇÃO DE ORDEM DE SERVIÇO")
    c.drawString(120 * mm, ALTURA_VIA - margem - 12 * mm, "MANUTENÇÃO")

    # Número da OS = número do chamado
    c.setFillColorRGB(0.82, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(LARGURA_VIA - margem - 4 * mm, ALTURA_VIA - margem - 9 * mm, f"Nº {numero_os}")
    c.setFillColorRGB(0, 0, 0)

    # Campos principais
    y = ALTURA_VIA - margem - 22 * mm
    x_fim = LARGURA_VIA - margem - 4 * mm

    _linha_com_valor(c, x0, y, x_fim, "Unidade Solicitante", chamado)
    y -= 7 * mm

    c.setFont("Helvetica", 9.5)
    c.drawString(x0, y, "Data")
    lx = x0 + c.stringWidth("Data", "Helvetica", 9.5) + 2 * mm
    c.line(lx, y - 1 * mm, lx + 18 * mm, y - 1 * mm)
    c.drawString(lx + 1 * mm, y + 0.5 * mm, data_impressao_str)
    c.drawString(lx + 22 * mm, y, "Funcionamento de plantão:")
    lx2 = lx + 22 * mm + c.stringWidth("Funcionamento de plantão:", "Helvetica", 9.5) + 2 * mm
    c.line(lx2, y - 1 * mm, x_fim, y - 1 * mm)
    y -= 7 * mm

    _linha_com_valor(c, x0, y, x_fim, "Responsável pela Execução da Atividade:", responsavel_nome)
    y -= 7 * mm

    # Manutenção: categorias do chamado marcadas + "Outros" em branco
    c.setFont("Helvetica", 9.5)
    c.drawString(x0, y, "Manutenção:")
    cx = x0 + c.stringWidth("Manutenção:", "Helvetica", 9.5) + 3 * mm
    cy = y
    for nome in categorias_nomes:
        if cx > x_fim - 30 * mm:
            cx = x0 + c.stringWidth("Manutenção:", "Helvetica", 9.5) + 3 * mm
            cy -= 6 * mm
        _checkbox(c, cx, cy + 2.6 * mm, 3 * mm, marcado=True)
        c.setFont("Helvetica", 8.5)
        c.drawString(cx + 4.2 * mm, cy, nome)
        cx += 4.2 * mm + c.stringWidth(nome, "Helvetica", 8.5) + 4 * mm

    if cx > x_fim - 45 * mm:
        cx = x0 + c.stringWidth("Manutenção:", "Helvetica", 9.5) + 3 * mm
        cy -= 6 * mm
    _checkbox(c, cx, cy + 2.6 * mm, 3 * mm, marcado=False)
    c.setFont("Helvetica", 8.5)
    c.drawString(cx + 4.2 * mm, cy, "Outros")
    lx3 = cx + 4.2 * mm + c.stringWidth("Outros", "Helvetica", 8.5) + 2 * mm
    c.line(lx3, cy - 1 * mm, x_fim, cy - 1 * mm)
    y = cy - 7 * mm

    # Descrição
    c.setFont("Helvetica", 9.5)
    c.drawString(x0, y, "Descrição do defeito ou atividade a ser executada:")
    y -= 6 * mm

    linhas_descricao = textwrap.wrap(descricao, width=95) if descricao else []
    for i in range(2):
        c.line(x0, y - 1 * mm, x_fim, y - 1 * mm)
        if i < len(linhas_descricao):
            c.setFont("Helvetica", 9)
            c.drawString(x0 + 1 * mm, y + 0.5 * mm, linhas_descricao[i])
        y -= 6 * mm

    # Situação da OS (em branco, preenchido depois manualmente)
    y -= 3 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(LARGURA_VIA / 2, y, "Situação da Ordem de serviço:")
    y -= 8 * mm

    c.setFont("Helvetica", 9.5)
    _checkbox(c, x0, y, 3.2 * mm)
    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "Executada")
    y -= 7 * mm

    _checkbox(c, x0, y, 3.2 * mm)
    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "Não Executada - Motivo")
    lx4 = x0 + 5 * mm + c.stringWidth("Não Executada - Motivo", "Helvetica", 9.5) + 2 * mm
    c.line(lx4, y - 3.8 * mm, x_fim, y - 3.8 * mm)
    y -= 7 * mm

    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "Observação:")
    lx5 = x0 + 5 * mm + c.stringWidth("Observação:", "Helvetica", 9.5) + 2 * mm
    c.line(lx5, y - 3.8 * mm, x_fim, y - 3.8 * mm)
    y -= 9 * mm
    c.line(x0, y - 1 * mm, x_fim, y - 1 * mm)

    # Assinaturas
    y = margem + 14 * mm
    largura_assinatura = (LARGURA_VIA - 2 * margem - 16 * mm) / 2
    c.line(x0, y, x0 + largura_assinatura, y)
    c.line(x0 + largura_assinatura + 16 * mm, y, x_fim, y)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x0 + largura_assinatura / 2, y - 5 * mm, "Responsável Unidade")
    c.drawCentredString(x0 + largura_assinatura + 16 * mm + largura_assinatura / 2, y - 5 * mm, "Responsável Telemedicina")

    # Rodapé
    c.setFont("Helvetica", 6.8)
    c.drawCentredString(
        LARGURA_VIA / 2, margem + 2 * mm,
        "CEMATEL - Central de Manutenção de Telemedicina - Av. Anita Garibaldi, 1555 sl 708, "
        "Centro Médico Garibaldi tel.: 3331-5414",
    )

    c.restoreState()


def gerar_pdf_os(chamado) -> bytes:
    import io

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    data_impressao_str = para_horario_local(datetime.now(timezone.utc)).strftime("%d/%m/%Y")
    categorias_nomes = [cat.nome for cat in chamado.categorias]
    descricao = (chamado.descricao or "").strip()

    _desenhar_via(
        c, y_offset=148 * mm, chamado=chamado.cliente_nome_snapshot,
        numero_os=chamado.numero_chamado, data_impressao_str=data_impressao_str,
        responsavel_nome=chamado.responsavel_nome_snapshot or "Não atribuído",
        categorias_nomes=categorias_nomes, descricao=descricao,
    )
    # Linha de corte
    c.setDash(3, 3)
    c.line(5 * mm, 148 * mm, 205 * mm, 148 * mm)
    c.setDash()

    _desenhar_via(
        c, y_offset=0, chamado=chamado.cliente_nome_snapshot,
        numero_os=chamado.numero_chamado, data_impressao_str=data_impressao_str,
        responsavel_nome=chamado.responsavel_nome_snapshot or "Não atribuído",
        categorias_nomes=categorias_nomes, descricao=descricao,
    )

    c.save()
    return buffer.getvalue()