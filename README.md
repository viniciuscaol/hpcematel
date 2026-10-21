# Help Desk Cematel

Sistema interno de chamados com FastAPI, PostgreSQL, Jinja2/HTMX, Alembic,
notificações WhatsApp via WAHA e rastreio de encomendas. Inclui histórico,
categorias múltiplas, SLA, mapa de atendimentos e ordem de serviço em PDF.

## Desenvolvimento com Docker Compose

1. Copie `.env.example` para `.env` e configure bancos, URL e chaves aleatórias.
   O banco legado é necessário para login e consulta de usuários/clientes;
   utilize uma conta de leitura e dados apropriados para desenvolvimento.
2. Execute `docker compose up -d --build`.
3. Execute `docker compose exec helpdesk_backend alembic upgrade head`.
4. Acesse `http://localhost:8000`. Configure a sessão WAHA apenas se for usar
   notificações. Credenciais válidas do legado devem ter perfil 1 e estar ativas.

O `.env` não é versionado. Nunca substitua exemplos por credenciais reais no
repositório. Não use produção como banco de testes.

## Permissões

| Operação | CAC | Técnico | Administrador |
|---|---|---|---|
| Consultar/criar chamados, comentar, anexar, alterar status/prioridade/responsável/rastreio | Sim | Sim | Sim |
| Alterar categorias de chamado não finalizado | Não | Sim | Sim |
| Assumir chamado | Não | Sim | Sim |
| Excluir chamado ou anexo | Não | Sim | Sim |
| Administrar categorias, prioridades, status e contatos | Não | Não | Sim |

A tabela descreve os papéis atuais; não existe isolamento por cliente/unidade.
Chamados excluídos ficam disponíveis para consulta histórica a usuários
autenticados, mas todas as rotas de alteração retornam 409. IDs inexistentes
nas rotas de alteração retornam 404. O papel padrão de quem não tem contato
ativo é CAC. A concessão inicial de ADMIN deve ser feita por um operador
autorizado no banco helpdesk; não há cadastro público de administradores.

## Testes

Com Python 3.12, instale `backend/requirements.txt` e
`backend/requirements-dev.txt` em um ambiente virtual. Dentro de `backend/`:

```sh
python -m pytest -v -m 'not integration'
```

Para a suíte completa, disponibilize um PostgreSQL exclusivo de testes e
defina `DATABASE_URL` no formato `postgresql+asyncpg://...`. O padrão é
`test_helpdesk` em `localhost:5433`, com usuário `test_user` e senha de teste
`test_pass`. Execute `python -m pytest -v`. Os testes de integração aplicam
migrações nesse banco. Os testes HTTP usam dependências simuladas e não
precisam acessar o banco legado nem enviar WhatsApp.

O workflow `CI / Testes` valida pull requests em um runner hospedado pelo
GitHub, com PostgreSQL descartável, sem segredos de produção nem deploy.
O workflow existente `Build e Deploy` continua no push da `main`.
Para impedir merges com falhas, configure proteção da `main` exigindo esse
check e pull request; a existência do workflow, sozinha, não impõe a regra.

## Operação e próximos passos

- [Deploy](docs/DEPLOY.md)
- [Segurança e resposta à exposição de dados](docs/SEGURANCA.md)

Próximas etapas de melhoria: consistência do SLA ao pausar/reabrir/trocar
prioridade; fila confiável de notificações; concorrência ao assumir chamados;
readiness do banco; restauração conjunta de banco e anexos; alertas e rollback.
O scheduler ainda roda dentro da API: não aumentar réplicas sem tratar a
execução duplicada de tarefas.
