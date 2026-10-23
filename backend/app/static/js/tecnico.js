// Atualiza o painel quando um cartão já não pode ser assumido.
(function () {
  document.body.addEventListener('htmx:responseError', function (event) {
    var detalhe = event.detail || {};
    var caminho = detalhe.pathInfo && detalhe.pathInfo.requestPath;
    if (detalhe.xhr && (detalhe.xhr.status === 409 || detalhe.xhr.status === 404)
        && /^\/chamados\/\d+\/assumir$/.test(caminho || '')) {
      window.location.assign('/tecnico?aviso=indisponivel');
    }
  });
})();
