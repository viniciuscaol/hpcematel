# Dois técnicos tentando assumir o mesmo chamado

Somente chamados não excluídos no status Aberto podem ser assumidos no painel.
Ao assumir, o backend bloqueia a linha no PostgreSQL até confirmar a mudança
para Em andamento, o responsável e os dois registros de histórico. A operação
relê o estado após obter o bloqueio, mesmo que a sessão já tenha carregado
uma versão antiga durante a validação da rota.

Se outro técnico tentar assumir ao mesmo tempo, sua transação espera a
primeira terminar. Após o commit do vencedor, a segunda encontra o estado
atualizado e recebe HTTP 409, sem trocar o responsável nem acrescentar outro
histórico. Repetir a operação com o mesmo usuário também retorna 409.
Um chamado excluído enquanto a requisição espera também é recusado. Se ele
deixar de existir, a rota responde 404.

No painel técnico, esses erros da operação Assumir levam a uma nova consulta
da lista e ao aviso: “Este chamado já foi assumido ou não está mais disponível.
A lista foi atualizada.” O aviso não é exibido para erros de outras operações
nem aceita texto arbitrário pela URL. O clique vencedor continua abrindo os
detalhes do chamado.

Não há mudança de schema nem migração nesta etapa. Esta proteção cobre a
operação Assumir. A edição manual de responsável e outras transições continuam
com suas regras próprias; não existe controle global de versão de todos os
campos do chamado.

## Testes em homologação

1. Abrir o painel técnico em duas sessões com usuários TECNICO diferentes.
2. Deixar o mesmo chamado em Aberto visível para ambos.
3. Clicar em Assumir nas duas sessões: apenas uma deve conseguir. A outra
   deve atualizar a lista e mostrar o aviso de indisponibilidade.
4. Conferir o responsável vencedor, status Em andamento e somente um par de
   eventos de status/responsável referente à assunção no histórico.
5. Em uma sessão que ainda tenha o cartão antigo, repetir o clique: deve
   atualizar a lista sem alterar o responsável.

Os testes de integração usam conexões reais e verificam a espera pelo lock
no PostgreSQL, com versão antiga já carregada na sessão perdedora. Também
verificam rollback conjunto dos campos e do histórico se o commit falhar.
