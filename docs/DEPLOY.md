# Deploy

Produção usa `k8s/` e namespace `chamados-cematel`; homologação usa
`k8s-homolog/` e `chamados-cematel-homolog`. Os manifests dependem de
ConfigMaps e Secrets criados no cluster: os diretórios não representam uma
instalação completa do zero. Os valores reais não devem entrar no Git.

O workflow `Build e Deploy` testa, publica a imagem com tag do commit,
aplica `alembic upgrade head` em homologação e atualiza o deployment.
Depois segue para o environment `producao`; a aprovação depende das regras
configuradas nesse environment no GitHub, não apenas do arquivo YAML.
Em produção também migra o banco e aguarda o rollout.

## Migrações e diagnóstico de falha

Os dois ambientes executam `scripts/migrate.sh`, que cria um Job com a imagem
do commit, `alembic upgrade head` e as referências existentes a
`helpdesk-config` e `helpdesk-secrets`. O Job tem limite de 600 segundos,
`backoffLimit: 0` e nome com ID e tentativa da execução. O deploy da aplicação
só começa após a condição `Complete=True` do Job. Um timeout não é tratado
como migração concluída.

Em falhas, o script imprime estado, descrição, eventos dos pods e os últimos
200 registros de log, sem consultar o conteúdo dos Secrets. O Job/pod não é
apagado imediatamente; o TTL permite limpeza 24 horas após o término.
Também é possível consultar pelo nome exibido no workflow:

```sh
kubectl -n chamados-cematel-homolog get jobs,pods
kubectl -n chamados-cematel-homolog describe job NOME_DO_JOB
kubectl -n chamados-cematel-homolog describe pods -l job-name=NOME_DO_JOB
kubectl -n chamados-cematel-homolog logs job/NOME_DO_JOB --all-containers=true --tail=200
```

`ImagePullBackOff`/`ErrImagePull` exigem verificar imagem, rede e autorização
no GHCR. `CreateContainerConfigError` exige conferir a existência das
referências de configuração no namespace. `Pending` pode indicar falta de
recursos ou restrições de agendamento; os eventos detalham a causa. Se o
container iniciar e o Alembic falhar, usar os logs para diagnosticar banco,
conectividade, credenciais ou migração específica.

O workflow antigo usava `kubectl run --rm -i`, que podia expirar em cerca de
60 segundos esperando o pod iniciar e removia a evidência ao falhar. Sem
eventos desse pod, não é possível determinar qual dessas causas ocorreu.
Após integrar uma correção do workflow, utilizar a execução do novo commit;
rerodar uma execução antiga continua usando o workflow antigo.

## Antes de integrar esta melhoria

- Revisar a matriz de permissões do README: exclusões passam a exigir
  TECNICO ou ADMIN. CAC continua com as demais operações já existentes.
- Validar o check de CI e o fluxo em homologação com usuários de cada papel.
- Se atualizar um checkout com Docker Compose que contém anexos rastreados,
  preservar os arquivos antes do pull, conforme `SEGURANCA.md`.
- A troca das chaves expostas é uma ação operacional separada: integrar o PR
  não invalida credenciais nem limpa o histórico antigo.

## Verificações em homologação

1. Fazer login como CAC: excluir chamado/anexo deve retornar 403 mesmo por
   requisição direta. Login como técnico e administrador deve permitir a ação.
2. Excluir um chamado de teste e tentar editar status, categoria, prioridade,
   responsável, comentário, anexo, rastreio e assumir: deve retornar 409.
3. Confirmar consulta histórica e geração de OS dos chamados excluídos.
4. Validar criação e atendimento de um chamado ativo.

## Recuperação e limitações atuais

O CronJob `backup-diario` envia dumps com rotação semanal e copia anexos para
o Drive. O job `restore-job-template.yaml` restaura apenas o banco em
homologação; ainda falta incluir anexos, verificar consistência e revisar
a correspondência de usuário/senha usada pelo job.

Não existe rollback automático no workflow. Antes de qualquer deploy com
migração, revisar compatibilidade com a versão anterior e disponibilidade de
backup restaurável. Reverter somente a imagem não desfaz o schema do banco.
