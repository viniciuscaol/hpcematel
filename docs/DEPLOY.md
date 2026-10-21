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
