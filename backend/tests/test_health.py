async def test_health_retorna_ok(client):
    resposta = await client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


async def test_login_sem_credenciais_da_erro_de_validacao(client):
    resposta = await client.post("/login", data={})
    assert resposta.status_code == 422  # faltam campos obrigatórios


async def test_pagina_login_carrega(client):
    resposta = await client.get("/login")
    assert resposta.status_code == 200
    assert "Chamados Cematel" in resposta.text or "usuário" in resposta.text.lower()