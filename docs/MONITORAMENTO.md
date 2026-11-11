# Monitoramento integrado

O painel fica em `/monitoramento` e usa a sessão existente do Help Desk. A rota HTML e todas as APIs exigem papel `ADMIN` ou `TECNICO`; usuários CAC recebem HTTP 403 mesmo acessando a URL diretamente.

## Coleta SSH

A API executa uma coleta SSH a cada 5 segundos (ajustável por `MONITOR_POLL_INTERVAL`). O servidor monitorado não precisa instalar agente: são consultados `/proc/stat`, `/proc/meminfo`, `/proc/loadavg`, `/proc/uptime` e `ps`. O cliente rejeita hosts desconhecidos e exige a chave do host previamente cadastrada em `known_hosts`.

Variáveis:
- `MONITOR_SSH_HOST`, `MONITOR_SSH_PORT`, `MONITOR_SSH_USER`
- `MONITOR_SSH_KEY`, `MONITOR_SSH_KNOWN_HOSTS`, `MONITOR_SSH_KEY_PASSPHRASE`
- `MONITOR_POLL_INTERVAL` (padrão 5 segundos)

No Kubernetes, crie um Secret chamado `monitoramento-ssh` em cada namespace, contendo `id_rsa` e `known_hosts`. O Deployment monta os arquivos em `/run/monitoramento-ssh`. O Secret `monitoramento-secrets` recebe as configurações sensíveis; `helpdesk-secrets` continua fornecendo a chave de API do WAHA.

## Alertas de CPU pelo WAHA

Configure `WAHA_GRUPO_MONITORAMENTO_ID` no Secret `helpdesk-secrets` de produção com o mesmo valor de `WAHA_GRUPO_ID` (grupo operacional de chamados). Não use `WAHA_GRUPO_DIRETORIA_ID`. O envio usa a URL e a sessão WAHA já definidas no ConfigMap `helpdesk-config`. A aplicação reutiliza a sessão WAHA existente.

- CPU acima de 30%: alerta ⚠️.
- CPU acima de 50%: urgência 🚨.
- CPU abaixo de 25%: normalização ✅.
- Uma mensagem é enviada ao mudar de faixa; não há repetição a cada coleta de 5 segundos. A faixa só volta a normal quando CPU cai abaixo de 25%, reduzindo oscilações.
- Toda mensagem de alerta contém a senha vigente do botão de emergência.
- Alertas de monitoramento podem ser entregues 24 horas; notificações normais de chamados continuam respeitando a janela comercial existente.

## Botão de pânico e senha rotativa

O botão exige a frase exata `REINICIAR`, uma sessão autenticada de ADMIN/TECNICO e a senha dinâmica. O backend executa exclusivamente o caminho absoluto definido em `MONITOR_PANIC_SCRIPT`; não há entrada para comandos livres.

Configurações no Secret `monitoramento-secrets`:
- `MONITOR_PANIC_PASSWORD`: senha inicial exclusiva, com pelo menos 16 caracteres. É usada apenas para inicializar a credencial.
- `MONITOR_PANIC_ENCRYPTION_KEY`: chave Fernet para cifrar a senha vigente persistida no banco.
- `MONITOR_PANIC_SCRIPT`: caminho absoluto do script remoto.
- `MONITOR_PANIC_SUDO=true`: usa `sudo -n` sem solicitar senha.

Gere a chave Fernet uma única vez em ambiente confiável e guarde-a no gerenciador de segredos:
```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

A primeira inicialização grava a senha inicial cifrada no banco e envia a credencial ao grupo operacional. Após cada acionamento autenticado, a senha anterior é invalidada e uma nova senha aleatória é gerada e enviada ao mesmo grupo junto com o nome de quem acionou, horário e resultado. As mensagens de alerta de CPU seguintes repetem a senha vigente para facilitar sua localização no grupo. A senha nunca é incluída na auditoria ou nos logs da aplicação.

A senha é compartilhada com todos os participantes do grupo operacional; qualquer integrante que veja a mensagem poderá conhecê-la. O endpoint continua exigindo papel ADMIN/TECNICO, frase de confirmação e limitação de tentativas. A senha é renovada após uma tentativa autenticada de execução, inclusive se o script retornar falha.

Se usar sudo, autorize no servidor monitorado somente o script específico, sem curingas e sem permitir comandos arbitrários. Valide o script manualmente antes de habilitar o botão. Há limite de 5 tentativas por minuto e intervalo mínimo de 120 segundos entre acionamentos.

## Fila WAHA e operação 24h

Alertas críticos são gravados na mesma fila persistente de mensagens do Help Desk, mas marcados para envio fora do horário comercial. Falhas de entrega permanecem na fila e usam o mecanismo existente de novas tentativas. A configuração do grupo de monitoramento é independente dos grupos de chamados e da gerência.

## Antes de habilitar em produção

1. Configurar o Secret SSH, o grupo operacional e as credenciais em homologação.
2. Validar coleta e alertas com carga controlada acima de 30% e 50%.
3. Confirmar a mensagem de normalização e que não há duplicação por coleta.
4. Testar a rotação com script inofensivo de homologação.
5. Conferir que a senha antiga deixa de funcionar e que a nova aparece no grupo.
6. Revisar sudo e o procedimento de retorno.
7. Só então configurar o script real e aprovar a implantação em produção.
