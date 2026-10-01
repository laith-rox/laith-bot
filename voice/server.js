const http=require('http');
const ORIGIN='https://laith-app-production.up.railway.app';
const port=Number(process.env.PORT||8080);
const server=http.createServer((req,res)=>{
  res.setHeader('Access-Control-Allow-Origin',ORIGIN);
  res.setHeader('Vary','Origin');
  res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers','Content-Type');
  if(req.method==='OPTIONS'){res.writeHead(204);return res.end();}
  if(req.method==='GET'&&(req.url==='/'||req.url==='/health')){
    res.writeHead(200,{'Content-Type':'application/json'});
    return res.end(JSON.stringify({ok:true,service:'laith-voice',execution:false}));
  }
  if(req.method!=='POST'||req.url!=='/session'){res.writeHead(404);return res.end('not found');}
  let body='';
  req.on('data',c=>{body+=c;if(body.length>131072)req.destroy();});
  req.on('end',async()=>{
    try{
      if(!process.env.OPENAI_API_KEY){res.writeHead(503);return res.end('voice key unavailable');}
      const form=new FormData();
      form.set('sdp',body);
      form.set('session',JSON.stringify({
        type:'realtime',
        model:'gpt-realtime',
        instructions:'أنت مساعد Laith Trading الصوتي لتحليل الذهب XAU/USD. تحدث بالعربية بوضوح واختصار. استخدم سياق السعر والفريم المرسل من التطبيق. تحليل ومراقبة فقط. لا تنفذ صفقات حقيقية، لا تغيّر إعدادات مالية، ولا تضمن الربح.',
        audio:{output:{voice:'marin'}}
      }));
      const upstream=await fetch('https://api.openai.com/v1/realtime/calls',{
        method:'POST',
        headers:{Authorization:'Bearer '+process.env.OPENAI_API_KEY},
        body:form
      });
      const text=await upstream.text();
      res.writeHead(upstream.status,{'Content-Type':upstream.headers.get('content-type')||'text/plain'});
      res.end(text);
    }catch(e){console.error('session error',e);res.writeHead(503);res.end('voice unavailable');}
  });
});
server.listen(port,'0.0.0.0',()=>console.log('laith-voice listening',port));
