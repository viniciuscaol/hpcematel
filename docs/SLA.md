# SLA e reabertura de chamados

## Regras vigentes

- Na criação, o prazo usa as horas da prioridade escolhida. O cálculo atual
  soma horas corridas e, se o vencimento cair no fim de semana, avança o
  vencimento para segunda-feira. Não é um calendário de horas comerciais
  nem inclui feriados.
- Status com `pausa_sla` suspendem a contagem. A troca entre dois status de
  pausa conserva o mesmo início. Ao sair da pausa, o tempo pausado é
  acrescentado ao prazo uma única vez.
- O dashboard conta como SLA estourado apenas chamados não excluídos,
  não finalizados e não pausados com prazo menor ou igual ao horário atual.
- Reabrir não concede um prazo novo e não desconta o período em que o chamado
  permaneceu finalizado. A data/local do fechamento anterior ficam em um
  evento no histórico; os campos atuais de resolução/cancelamento/local são
  limpos. O marcador do alerta de SLA é reiniciado, permitindo novo alerta
  pelo monitor se o chamado reaberto estiver próximo do prazo ou atrasado.
- Ao resolver novamente, o fechamento usa a data atual e apenas a localização
  informada nessa resolução. GPS anterior não é reutilizado. Trocar entre
  Resolvido e Cancelado também preserva o fechamento anterior no histórico e
  atualiza os campos conforme o status de destino.
  A localização do fechamento anterior no histórico só é exibida para ADMIN,
  seguindo a mesma restrição da localização atual na tela.
- Trocar a prioridade preserva o prazo registrado. Alterar essa política exige
  definir se o novo SLA vale desde a abertura ou desde a mudança e como tratar
  pausas já ocorridas; esse recálculo não está implementado.
- Tempo médio de resolução e percentual dentro do SLA consideram apenas
  chamados atualmente em Resolvido, com data de resolução e não excluídos.
  Datas antigas em chamados reabertos/cancelados não entram nesses indicadores.
- Status inexistente/inativo e prioridade inexistente/inativa ou com horas de
  SLA não positivas são rejeitados nas alterações. A criação também valida
  a prioridade. As rotas retornam 422 para essas escolhas inválidas, sem salvar
  a mudança nem disparar suas notificações.

Os registros antigos não são reescritos em lote. As métricas já filtram pelo
status atual, e os campos de fechamento são corrigidos nas transições futuras.
Nenhuma mudança de schema é necessária.

## Testes em homologação

1. Escolher chamado atrasado e anotar a contagem do dashboard. Mover para
   Aguardando cliente ou Aguardando Correios: ele deve sair da contagem de
   atrasados. Os demais chamados não mudam de classificação.
2. Alternar entre os dois status de pausa. Retomar o atendimento e conferir
   que o prazo foi estendido pelo tempo total pausado, sem reiniciar a pausa
   na troca de status.
3. Resolver e depois reabrir um chamado de teste. Conferir o evento do
   fechamento anterior na timeline, o prazo mantido e a retirada do chamado
   dos indicadores de resolução.
4. Resolver novamente, inclusive sem GPS. A data deve ser a nova, e o mapa
   não deve aproveitar a localização de um fechamento anterior.
5. Trocar prioridade: a alteração deve aparecer no histórico, mantendo o
   prazo. A regra vale também para chamados já em pausa.

O marcador de alerta representa inclusão na fila, não confirmação de entrega
ao WhatsApp. Reenvios e operação da fila: [Notificações](NOTIFICACOES.md).
