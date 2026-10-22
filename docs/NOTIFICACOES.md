# Notificações WhatsApp

## Como funciona

Toda notificação com destino configurado é gravada em `notificacao_pendente`
antes de qualquer acesso ao WAHA. Criação de chamado (inclusive rastreio
inicial), mudança para status finalizador e atribuição individual confirmam
a alteração e suas notificações na mesma transação. Se a gravação da fila
falhar, a alteração também não é confirmada. Repetir o mesmo status ou
responsável após a confirmação não cria um novo aviso dessa operação.

O monitor de SLA confirma o marcador `sla_notificado_status` junto com a
mensagem enfileirada. Esse campo significa **estado enfileirado**, não mensagem
entregue. Sem destino, o alerta não é marcado e pode ser avaliado novamente
quando a configuração for corrigida. A atualização de rastreio e a inclusão
de seus avisos também compartilham a transação do monitor existente.

Um destino configurado com chave WAHA temporariamente ausente continua
acumulando mensagens. O processador só tenta enviá-las quando a chave existe.
Eventos sem destino configurado não podem ser enfileirados: deixam aviso no
log, mas não impedem o atendimento. Não é possível recuperar retroativamente
mensagens que a versão anterior perdeu ou descartou.

## Processamento e reenvio

- O scheduler verifica a fila a cada minuto. Envia somente entre 08h e 19h,
  no horário da Bahia, todos os dias, preservando a regra anterior. Não há
  calendário de feriados. Mensagens fora da janela conservam o horário da
  ocorrência no texto.
- Cada execução tenta no máximo 20 mensagens elegíveis. Um lote lento ou
  fila acumulada pode aumentar a espera além de um minuto. O mesmo job do
  scheduler não executa duas instâncias simultaneamente no mesmo processo.
- A falha fica registrada com número de tentativas, horário, próximo envio
  e erro resumido. Os intervalos após falhas são 1, 2, 4, 8, 16 e 30 minutos;
  depois permanecem em 30 minutos. Não há descarte por número de tentativas.
- Não são guardados no erro corpo de resposta, URL, chave nem conteúdo da
  mensagem. Exemplos: `HTTP 401`, `HTTP 503`, `Timeout no WAHA`.
- Uma mensagem em espera de reenvio não bloqueia outras. O processador usa
  `FOR UPDATE SKIP LOCKED`, mantendo a linha bloqueada durante a chamada HTTP,
  para que dois processadores novos não peguem o mesmo item simultaneamente.
- A resposta HTTP bem-sucedida do WAHA remove o item e confirma a transação
  imediatamente, antes de continuar o lote. Isso representa aceite do WAHA,
  **não confirmação de entrega/leitura pelo destinatário**.

Se o WAHA aceitar uma mensagem e a conexão cair antes da resposta, ou se o
processo/banco falhar antes de confirmar a remoção, pode haver reenvio e
duplicidade. Esta implementação prioriza não perder a mensagem e não promete
envio único. Os registros guardam o evento original: um alerta pode chegar
depois de o chamado já ter mudado, caso o serviço tenha ficado indisponível.
Os outros monitores ainda rodam dentro da API; esta alteração não resolve
toda a concorrência de múltiplas réplicas da aplicação.

## Deploy e compatibilidade

A revisão Alembic `f2d4a6b8c901` acrescenta quatro campos e um índice. Mensagens
pendentes existentes são preservadas; recebem zero tentativas e próxima
tentativa preenchida para voltar ao processamento. Inserts da versão anterior
continuam aceitos pelos valores padrão. Não há exclusão de mensagens durante
a migração.

O workflow aplica a migração antes de atualizar os pods. Não fazer downgrade
do schema com o processador novo ativo. A versão antiga da aplicação pode
ignorar as colunas adicionais, mas retorna ao comportamento anterior de
reenvio; sobreposição entre processadores antigos e novos durante rollout
não tem a proteção de concorrência do novo código nos dois lados.

## Acompanhamento

No banco helpdesk, sem consultar conteúdo nem destinatários:

```sql
SELECT count(*) AS pendentes,
       count(*) FILTER (WHERE tentativas > 0) AS com_falhas,
       min(criado_em) AS mais_antiga
FROM notificacao_pendente;

SELECT id, tentativas, ultima_tentativa_em, proxima_tentativa_em, ultimo_erro
FROM notificacao_pendente
ORDER BY criado_em, id
LIMIT 20;
```

Fila crescendo com `HTTP 401` exige conferir a chave do WAHA. Falhas de
conexão/timeout exigem conferir serviço e rede; erros de sessão exigem
conferir a sessão no WAHA. Não apagar a fila para ocultar o problema: o
processamento retoma quando a causa for resolvida e chegar a próxima tentativa.
Alertas de monitoramento e uma tela administrativa da fila ficam para uma
etapa posterior.

## Validação em homologação

1. Usar destino e sessão de teste, separados dos grupos de produção.
2. Criar um chamado e conferir a mensagem na fila antes do aceite do WAHA.
3. Simular WAHA indisponível: o chamado deve salvar normalmente; a mensagem
   deve permanecer na fila com tentativas/erro/próximo envio.
4. Restabelecer o WAHA e aguardar a próxima tentativa na janela permitida:
   a mensagem deve ser aceita e removida da fila.
5. Conferir alerta de SLA: uma única inclusão por estado; falha de envio
   continua na fila, sem depender de gerar outro alerta.
6. Repetir o mesmo status ou responsável: não deve criar novo aviso. Alterar
   efetivamente o campo deve continuar notificando conforme o fluxo anterior.

Os testes automatizados usam respostas HTTP simuladas. Nenhum deles envia
mensagens reais.
