# Monitoramento integrado

O painel fica em `/monitoramento` e usa a sessão existente do Help Desk. A rota HTML e todas as APIs exigem papel `ADMIN` ou `TECNICO`; usuários CAC recebem HTTP 403 mesmo acessando a URL diretamente.

## Coleta

A API executa uma coleta SSH a cada 5 segundos (ajustável por `MONITOR_POLL_INTERVAL`). O servidor monitorado não precisa instalar agente: são consultados `/proc/stat`, `/proc/meminfo`, `/proc/loadavg`, `/proc/uptime` e `ps`. A chave SSH deve ser exclusiva, somente leitura quando possível, e a chave do host deve estar previamente cadastrada em `known_hosts`. O cliente rejeita hosts desconhecidos.

Variáveis:
- `MONITOR_SSH_HOST`, `MONITOR_SSH_PORT`, `MONITOR_SSH_USER`
- `MONITOR_SSH_KEY`, `MONITOR_SSH_KNOWN_HOSTS`, `MONITOR_SSH_KEY_PASSPHRASE`
- `MONITOR_POLL_INTERVAL` (padrão 5 segundos)

No Kubernetes, crie um Secret chamado `monitoramento-ssh` em cada namespace que receberá a aplicação, contendo as chaves `id_rsa` e `known_hosts`. O Deployment monta esse Secret em `/run/monitoramento-ssh`. O Secret é opcional para permitir que o Help Desk continue funcionando antes da configuração; sem SSH, o painel informa indisponibilidade.

Exemplo de criação (executar localmente, sem versionar os arquivos):
```sh
kubectl -n chamados-cematel create secret generic monitoramento-ssh \
  --from-file=id_rsa=/caminho/da/chave \
  --from-file=known_hosts=/caminho/known_hosts
kubectl -n chamados-cematel-homolog create secret generic monitoramento-ssh \
  --from-file=id_rsa=/caminho/da/chave \
  --from-file=known_hosts=/caminho/known_hosts
```

Configure também `MONITOR_SSH_HOST`, `MONITOR_SSH_PORT` e `MONITOR_SSH_USER` no ConfigMap/Secret `helpdesk-config`/`helpdesk-secrets`. O usuário SSH deve ter somente as permissões necessárias para ler métricas do sistema.

## Botão de pânico

O botão exige a frase exata `REINICIAR` e uma senha separada do login do Help Desk. O backend executa exclusivamente o caminho absoluto definido em `MONITOR_PANIC_SCRIPT`; não existe campo para comandos livres. Configure:
- `MONITOR_PANIC_PASSWORD`: senha longa, exclusiva e guardada no Secret `helpdesk-secrets`.
- `MONITOR_PANIC_SCRIPT`: caminho absoluto do script remoto.
- `MONITOR_PANIC_SUDO=true`: usa `sudo -n` (sem solicitar senha) para o script.

Se usar sudo, autorize no servidor monitorado somente o script específico, sem curingas e sem permitir comandos arbitrários. Valide o script manualmente antes de habilitar o botão. Há intervalo mínimo de 120 segundos entre acionamentos.

Cada tentativa que chega à execução é registrada no banco Help Desk com código, login, nome do usuário, horário, resultado e detalhe. A senha nunca é armazenada no histórico. O histórico de CPU/RAM também fica no PostgreSQL e é mantido por janela diária.

## Antes de habilitar em produção

1. Configurar Secret SSH e variáveis em homologação.
2. Validar coleta, permissões e histórico por pelo menos um ciclo de uso.
3. Testar o botão somente com script inofensivo de homologação.
4. Revisar a regra de sudo e o procedimento de retorno.
5. Só então configurar o script real e a senha de emergência em produção.
