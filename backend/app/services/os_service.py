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

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "LOGO_TELEMEDICINA.png")

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
    c.setFont("Helvetica", 10)
    c.drawString(x_ini, y, label)
    largura_label = c.stringWidth(label, "Helvetica", 10)
    x_valor = x_ini + largura_label + 2 * mm
    c.line(x_valor, y - 1 * mm, x_fim, y - 1 * mm)
    if valor:
        c.setFont("Helvetica", 10)
        c.drawString(x_valor + 1.5 * mm, y + 0.5 * mm, valor)


def _desenhar_via(c, y_offset, chamado, numero_os, data_impressao_str, responsavel_nome, categorias_nomes, descricao):
    c.saveState()
    c.translate(0, y_offset)

    margem = 5 * mm
    c.setLineWidth(1)
    c.roundRect(margem, margem, LARGURA_VIA - 2 * margem, ALTURA_VIA - 2 * margem, 4 * mm, stroke=1, fill=0)

    x0 = margem + 4 * mm
    y_topo = ALTURA_VIA - margem - 6 * mm

    # ==========================
    # CABEÇALHO REESTRUTURADO
    # ==========================

    # 1. Tipo de visita (esquerda)
    c.setFont("Helvetica-Bold", 10)
    _checkbox(c, x0, y_topo, 3.5 * mm)
    c.drawString(x0 + 5 * mm, y_topo - 2.8 * mm, "VISITA CORRETIVA")
    
    _checkbox(c, x0, y_topo - 7 * mm, 3.5 * mm)
    c.drawString(x0 + 5 * mm, y_topo - 9.8 * mm, "VISITA PREVENTIVA")

    # 2. Logo (centro, ainda maior)
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(
                LOGO_PATH, x0 + 38 * mm, ALTURA_VIA - margem - 22 * mm,
                width=65 * mm, height=21 * mm, preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # 3. Título da OS (Direita da logo, sem "Solicitação de", MANUTENÇÃO centralizado)
    x_titulo = x0 + 108 * mm
    
    c.setFont("Helvetica-Bold", 12)
    texto_ordem = "ORDEM DE SERVIÇO"
    c.drawString(x_titulo, y_topo - 2 * mm, texto_ordem)
    
    c.setFont("Helvetica-Bold", 11)
    texto_manutencao = "MANUTENÇÃO"
    
    # Cálculo para centralizar a palavra MANUTENÇÃO abaixo de ORDEM DE SERVIÇO
    largura_ordem = c.stringWidth(texto_ordem, "Helvetica-Bold", 12)
    largura_manutencao = c.stringWidth(texto_manutencao, "Helvetica-Bold", 11)
    x_manutencao = x_titulo + (largura_ordem - largura_manutencao) / 2
    
    c.drawString(x_manutencao, y_topo - 7 * mm, texto_manutencao)

    # 4. Número da OS (extrema direita)
    c.setFillColorRGB(0.82, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(LARGURA_VIA - margem - 4 * mm, y_topo - 4.5 * mm, f"Nº {numero_os}")
    c.setFillColorRGB(0, 0, 0)

    # ==========================
    # CORPO DA OS
    # ==========================
    
    y = ALTURA_VIA - margem - 25 * mm
    x_fim = LARGURA_VIA - margem - 4 * mm

    _linha_com_valor(c, x0, y, x_fim, "Unidade Solicitante", chamado)
    y -= 7 * mm

    c.setFont("Helvetica", 10)
    c.drawString(x0, y, "Data")
    lx = x0 + c.stringWidth("Data", "Helvetica", 10) + 2 * mm
    c.line(lx, y - 1 * mm, lx + 18 * mm, y - 1 * mm)
    c.drawString(lx + 1 * mm, y + 0.5 * mm, data_impressao_str)
    c.drawString(lx + 22 * mm, y, "Funcionamento de plantão:")
    lx2 = lx + 22 * mm + c.stringWidth("Funcionamento de plantão:", "Helvetica", 10) + 2 * mm
    c.line(lx2, y - 1 * mm, x_fim, y - 1 * mm)
    y -= 7 * mm

    _linha_com_valor(c, x0, y, x_fim, "Responsável pela Execução da Atividade:", responsavel_nome)
    y -= 7 * mm

    # Manutenção: categorias do chamado marcadas + "Outros" em branco
    c.setFont("Helvetica", 10)
    c.drawString(x0, y, "Manutenção:")
    cx = x0 + c.stringWidth("Manutenção:", "Helvetica", 10) + 3 * mm
    cy = y
    for nome in categorias_nomes:
        if cx > x_fim - 30 * mm:
            cx = x0 + c.stringWidth("Manutenção:", "Helvetica", 10) + 3 * mm
            cy -= 6 * mm
        _checkbox(c, cx, cy + 2.6 * mm, 3 * mm, marcado=True)
        c.setFont("Helvetica", 9)
        c.drawString(cx + 4.2 * mm, cy, nome)
        cx += 4.2 * mm + c.stringWidth(nome, "Helvetica", 9) + 4 * mm

    if cx > x_fim - 45 * mm:
        cx = x0 + c.stringWidth("Manutenção:", "Helvetica", 10) + 3 * mm
        cy -= 6 * mm
    _checkbox(c, cx, cy + 2.6 * mm, 3 * mm, marcado=False)
    c.setFont("Helvetica", 9)
    c.drawString(cx + 4.2 * mm, cy, "Outros")
    lx3 = cx + 4.2 * mm + c.stringWidth("Outros", "Helvetica", 9) + 2 * mm
    c.line(lx3, cy - 1 * mm, x_fim, cy - 1 * mm)
    y = cy - 7 * mm

    # Descrição
    c.setFont("Helvetica", 10)
    c.drawString(x0, y, "Descrição do defeito ou atividade a ser executada:")
    y -= 6 * mm

    linhas_descricao = textwrap.wrap(descricao, width=95) if descricao else []
    for i in range(2):
        c.line(x0, y - 1 * mm, x_fim, y - 1 * mm)
        if i < len(linhas_descricao):
            c.setFont("Helvetica", 9.5)
            c.drawString(x0 + 1 * mm, y + 0.5 * mm, linhas_descricao[i])
        y -= 6 * mm

    # ==========================
    # RODAPÉ / ASSINATURAS (ESPAÇAMENTO AJUSTADO)
    # ==========================
    
    # Situação da OS (Menos espaço vazio acima)
    y -= 1 * mm
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(LARGURA_VIA / 2, y, "Situação da Ordem de serviço:")
    y -= 5 * mm # Reduzido (era 8mm)

    c.setFont("Helvetica", 10)
    _checkbox(c, x0, y, 3.5 * mm)
    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "Executada")
    y -= 6 * mm # Reduzido (era 7mm)

    _checkbox(c, x0, y, 3.5 * mm)
    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "Não Executada - Motivo")
    lx4 = x0 + 5 * mm + c.stringWidth("Não Executada - Motivo", "Helvetica", 10) + 2 * mm
    c.line(lx4, y - 3.8 * mm, x_fim, y - 3.8 * mm)
    y -= 6 * mm # Reduzido (era 7mm)

    c.drawString(x0 + 5 * mm, y - 2.8 * mm, "Observação:")
    lx5 = x0 + 5 * mm + c.stringWidth("Observação:", "Helvetica", 10) + 2 * mm
    c.line(lx5, y - 3.8 * mm, x_fim, y - 3.8 * mm)
    y -= 6 * mm # Reduzido (era 9mm)
    c.line(x0, y - 1 * mm, x_fim, y - 1 * mm)

    # Assinaturas (Linha subiu de 14mm para 17mm para aumentar o espaço para escrita manual)
    y = margem + 17 * mm 
    largura_assinatura = (LARGURA_VIA - 2 * margem - 16 * mm) / 2
    c.line(x0, y, x0 + largura_assinatura, y)
    c.line(x0 + largura_assinatura + 16 * mm, y, x_fim, y)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x0 + largura_assinatura / 2, y - 4 * mm, "Responsável Unidade")
    c.drawCentredString(x0 + largura_assinatura + 16 * mm + largura_assinatura / 2, y - 4 * mm, "Responsável Telemedicina")

    # Rodapé Endereço
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(
        LARGURA_VIA / 2, margem + 3 * mm,
        "CEMATEL - Central de Manutenção da Telemedicina - Av. Anita Garibaldi, 1555 sl 701, "
        "Centro Médico Garibaldi Tel.: (71) 3331-5414",
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