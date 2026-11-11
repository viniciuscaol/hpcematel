(() => {
  const $ = (id) => document.getElementById(id);
  const dialog = $("dialog-panico");
  let historico = [];
  function gauge(id, valorId, valor) {
    const n = Math.max(0, Math.min(100, Number(valor || 0)));
    $(id).style.background = `conic-gradient(var(--color-primary,#2C3E8C) ${n * 3.6}deg,#e5e7eb 0deg)`;
    $(valorId).textContent = `${n.toFixed(1)}%`;
  }
  function duracao(seg) {
    const d=Math.floor(seg/86400), h=Math.floor(seg%86400/3600), m=Math.floor(seg%3600/60);
    return `${d}d ${h}h ${m}min`;
  }
  function desenharGrafico() {
    const c=$("monitor-chart"), ctx=c.getContext("2d"), w=c.width=c.clientWidth*devicePixelRatio, h=c.height=180*devicePixelRatio;
    ctx.clearRect(0,0,w,h); if(!historico.length)return;
    const max=100, pad=22*devicePixelRatio;
    [["cpu","#2C3E8C"],["memoria","#16a34a"]].forEach(([k,cor])=>{
      ctx.beginPath();ctx.strokeStyle=cor;ctx.lineWidth=2*devicePixelRatio;
      historico.forEach((p,i)=>{const x=pad+i*(w-2*pad)/Math.max(1,historico.length-1),y=h-pad-(Number(p[k])/max)*(h-2*pad);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});
      ctx.stroke();
    });
  }
  async function atualizar() {
    try {
      const [s,h]=await Promise.all([fetch("/api/monitoramento/status"),fetch("/api/monitoramento/historico?minutos=60")]);
      if(!s.ok||!h.ok)throw new Error("Falha ao consultar monitoramento");
      const d=await s.json();historico=await h.json();
      $("monitor-status").textContent=d.online?"Servidor conectado":"Servidor indisponível";
      $("abrir-panico").disabled=!d.panic_configurado;
      $("abrir-panico").textContent=d.panic_configurado?"ACIONAR EMERGÊNCIA":"EMERGÊNCIA NÃO CONFIGURADA";
      $("monitor-status").className="monitor-status "+(d.online?"online":"offline");
      if(!d.online){$("cpu-host").textContent=d.erro||"Sem conexão";return}
      gauge("gauge-cpu","cpu-valor",d.cpu);gauge("gauge-ram","ram-valor",d.memoria);
      $("cpu-host").textContent=d.host;$("ram-detalhe").textContent=`${d.memoria_usada_mb} MB de ${d.memoria_total_mb} MB`;
      $("host").textContent=d.host;$("load").textContent=(d.load||[]).join(" / ");$("uptime").textContent=duracao(d.uptime_segundos||0);
      $("swap").textContent=`${d.swap_total_mb-(d.swap_livre_mb||0)} / ${d.swap_total_mb} MB`;
      $("processos").innerHTML=(d.processos||[]).slice(0,8).map(p=>`<tr><td>${String(p.nome).replace(/[&<>"]/g,"")}</td><td>${p.pid}</td><td>${p.cpu.toFixed(1)}%</td><td>${p.memoria.toFixed(1)}%</td></tr>`).join("")||'<tr><td colspan="4">Sem dados</td></tr>';
      desenharGrafico();
    } catch(e) {$("monitor-status").textContent="Falha na consulta";$("monitor-status").className="monitor-status offline"}
  }
  $("abrir-panico").addEventListener("click",()=>{ $("form-panico").reset();$("panico-mensagem").textContent="";dialog.showModal() });
  $("cancelar-panico").addEventListener("click",()=>dialog.close());
  $("form-panico").addEventListener("submit",async e=>{
    e.preventDefault();const b=e.submitter;b.disabled=true;$("panico-mensagem").textContent="Executando...";
    try{
      const r=await fetch("/api/monitoramento/panico",{method:"POST",body:new FormData(e.currentTarget)});
      const data=await r.json();$("panico-mensagem").textContent=data.mensagem||data.detail||"Solicitação concluída.";
      if(r.ok)e.currentTarget.reset();
    }catch(_){$("panico-mensagem").textContent="Não foi possível concluir a solicitação."}
    finally{b.disabled=false}
  });
  window.addEventListener("resize",desenharGrafico);atualizar();setInterval(atualizar,5000);
})();