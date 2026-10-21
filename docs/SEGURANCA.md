# Segurança e exposição anterior de dados

## O que esta alteração resolve

Remove da árvore atual do Git os cookies, o export de grupos WhatsApp,
os anexos de execução e o comando que continha uma chave WAHA literal.
As cópias locais de trabalho não são apagadas pela preparação da alteração.
O `.gitignore` impede inclusão acidental desses caminhos em novos commits.
Anexos operacionais devem permanecer nos volumes da aplicação e no backup.

**Isso não apaga versões anteriores, branches, forks, clones ou cópias em cache
e não invalida nenhuma credencial.** Antes de aplicar a remoção em um checkout
usado por Docker Compose, preserve `data/anexos` fora do checkout e confirme
o backup: o Git pode remover arquivos antes rastreados durante a atualização.
Os PVCs de Kubernetes não são removidos por esta alteração.

## Ações operacionais pendentes

1. Substituir a chave WAHA exposta, se ela tiver sido utilizada. Atualizar
   tanto `waha-secrets` quanto `helpdesk-secrets` com a chave correspondente
   e reiniciar os workloads de forma coordenada. Não colar a chave em issues,
   PRs ou comandos versionados. Confirmar envio somente a um destino de teste.
2. Considerar o cookie versionado comprometido. Para invalidar todos os JWTs
   emitidos, trocar `JWT_SECRET_KEY` no secret do backend e reiniciar o
   deployment. Isso encerra as sessões de todos os usuários; fazer em janela
   acordada. Não é necessário divulgar o token antigo.
3. Identificar se os anexos e dados de grupos eram reais e avaliar o alcance
   da exposição com o responsável pelos dados.
4. Planejar a remoção dos caminhos sensíveis de todo o histórico e das refs
   relevantes. A reescrita exige coordenação, preservação de dados e atualização
   dos clones; não executar force-push sem um plano revisado.
5. Configurar proteção da `main`, revisão por PR e check `CI / Testes` obrigatório.

Não foram executadas alterações em secrets, reinícios de produção, proteção
de branch ou reescrita do histórico por este PR.

## Limites e melhorias seguintes

O login continua dependente do legado e faz comparação direta da senha
retornada por ele. Uma migração para hashes ou identidade centralizada deve
ser coordenada com o sistema legado. A sessão atual é validada pelo JWT;
inativação no legado não revoga imediatamente tokens já emitidos.

Upload ainda valida extensão e tamanho, mas lê o conteúdo completo antes
de rejeitar arquivos maiores que 15 MB. Melhorias de streaming, inspeção de
conteúdo, limites no ingress e cotas ficam para uma etapa posterior.
