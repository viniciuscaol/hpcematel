"""
Instância única e compartilhada do Jinja2Templates.

Todos os routers devem importar `templates` deste módulo, em vez de
criar suas próprias instâncias de Jinja2Templates. Isso garante que
filtros (como formatação de data) e variáveis globais (como app_name)
fiquem disponíveis em qualquer template do sistema, sem duplicação.
"""
from fastapi.templating import Jinja2Templates

from app.utils.datas import formatar_data_br

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["data_br"] = formatar_data_br