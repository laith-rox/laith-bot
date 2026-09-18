// Laith MT5 Demo Bridge EA — DEMO ONLY.
// Polls the isolated Laith Execution Bridge over HTTPS.
// Live accounts are rejected. Gold only. Fixed 0.01 lot. One open gold position max.
#property strict

#include <Trade/Trade.mqh>
CTrade trade;

input string BridgeBaseUrl = "";
input string BridgeClientToken = "";
input int PollSeconds = 2;
input bool LocalKillSwitch = true;
input double DemoLots = 0.01;
input long MagicNumber = 56002;

string g_base_url = "";

bool IsDemoAccount()
{
   return (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO);
}

bool IsGoldSymbol()
{
   return (StringFind(_Symbol,"XAUUSD") >= 0);
}

bool HasOpenGoldPosition()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket>0 && PositionSelectByTicket(ticket))
      {
         string sym=PositionGetString(POSITION_SYMBOL);
         if(StringFind(sym,"XAUUSD")>=0)
            return true;
      }
   }
   return false;
}

bool SafeInputs(string side,double volume,double sl,double tp)
{
   if(!IsDemoAccount()) return false;
   if(!IsGoldSymbol()) return false;
   if(LocalKillSwitch) return false;
   if(HasOpenGoldPosition()) return false;
   if(MathAbs(DemoLots-0.01)>0.0000001) return false;
   if(MathAbs(volume-0.01)>0.0000001) return false;
   if(sl<=0 || tp<=0) return false;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return false;

   if(side=="BUY" && !(sl<tick.ask && tp>tick.ask)) return false;
   if(side=="SELL" && !(sl>tick.bid && tp<tick.bid)) return false;
   return (side=="BUY" || side=="SELL");
}

string ResultToString(char &result[])
{
   if(ArraySize(result)<=0) return "";
   return CharArrayToString(result,0,-1,CP_UTF8);
}

int HttpGet(string url,string &body)
{
   char data[];
   char result[];
   string response_headers;
   string headers="X-Bridge-Token: "+BridgeClientToken+"\r\n";
   ResetLastError();
   int code=WebRequest("GET",url,headers,5000,data,result,response_headers);
   body=ResultToString(result);
   if(code<0)
      Print("LAITH_BRIDGE_HTTP_GET_ERROR err=",GetLastError()," url=",url);
   return code;
}

int HttpPostJson(string url,string json,string &body)
{
   char data[];
   char result[];
   string response_headers;
   StringToCharArray(json,data,0,WHOLE_ARRAY,CP_UTF8);
   if(ArraySize(data)>0)
      ArrayResize(data,ArraySize(data)-1);
   string headers="Content-Type: application/json\r\nX-Bridge-Token: "+BridgeClientToken+"\r\n";
   ResetLastError();
   int code=WebRequest("POST",url,headers,5000,data,result,response_headers);
   body=ResultToString(result);
   if(code<0)
      Print("LAITH_BRIDGE_HTTP_POST_ERROR err=",GetLastError()," url=",url);
   return code;
}

bool VerifyCommand(string key,string ts,string symbol,string side,string volume,string sl,string tp,string sig)
{
   string url=g_base_url+
      "/verify?key="+key+
      "&ts="+ts+
      "&symbol="+symbol+
      "&side="+side+
      "&volume="+volume+
      "&sl="+sl+
      "&tp="+tp+
      "&sig="+sig;
   string body="";
   int code=HttpGet(url,body);
   return (code==200 && StringFind(body,"OK")>=0);
}

void AckCommand(string key,bool ok,long retcode,ulong ticket)
{
   string body="";
   string json="{\"key\":\""+key+"\",\"ok\":"+(ok?"true":"false")+
               ",\"reason\":\"retcode_"+IntegerToString((int)retcode)+"\",\"ticket\":\""+
               IntegerToString((int)ticket)+"\"}";
   int code=HttpPostJson(g_base_url+"/ack",json,body);
   Print("LAITH_BRIDGE_ACK key=",key," http=",code," body=",body);
}

bool ExecuteDemo(string side,double volume,double sl,double tp,string id)
{
   if(!SafeInputs(side,volume,sl,tp))
   {
      Print("LAITH_BRIDGE_REJECT id=",id," reason=local_safety_gate");
      AckCommand(id,false,0,0);
      return false;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);

   bool ok=false;
   if(side=="BUY")
      ok=trade.Buy(DemoLots,_Symbol,0,sl,tp,"LaithDemo:"+id);
   else if(side=="SELL")
      ok=trade.Sell(DemoLots,_Symbol,0,sl,tp,"LaithDemo:"+id);

   long retcode=(long)trade.ResultRetcode();
   ulong ticket=trade.ResultOrder();
   Print("LAITH_BRIDGE_EXEC id=",id," side=",side," ok=",ok," retcode=",retcode," ticket=",ticket);
   AckCommand(id,ok,retcode,ticket);
   return ok;
}

void PollBridge()
{
   if(LocalKillSwitch) return;
   if(HasOpenGoldPosition()) return;

   string body="";
   int code=HttpGet(g_base_url+"/next",body);
   if(code==423 || code==204) return;
   if(code!=200) return;
   if(body=="NONE" || StringLen(body)<4) return;

   string parts[];
   int n=StringSplit(body,'|',parts);
   // CMD|DEMO|key|ts|symbol|side|volume|sl|tp|sig
   if(n!=10 || parts[0]!="CMD" || parts[1]!="DEMO")
   {
      Print("LAITH_BRIDGE_BAD_COMMAND body=",body);
      return;
   }

   string key=parts[2];
   string ts=parts[3];
   string symbol=parts[4];
   string side=parts[5];
   string volume_s=parts[6];
   string sl_s=parts[7];
   string tp_s=parts[8];
   string sig=parts[9];

   if(StringFind(symbol,"XAUUSD")<0)
   {
      Print("LAITH_BRIDGE_REJECT id=",key," reason=symbol");
      return;
   }

   if(!VerifyCommand(key,ts,symbol,side,volume_s,sl_s,tp_s,sig))
   {
      Print("LAITH_BRIDGE_REJECT id=",key," reason=verify_failed");
      return;
   }

   double volume=StringToDouble(volume_s);
   double sl=StringToDouble(sl_s);
   double tp=StringToDouble(tp_s);
   ExecuteDemo(side,volume,sl,tp,key);
}

int OnInit()
{
   if(!IsDemoAccount())
   {
      Print("LAITH_BRIDGE_DISABLED live_account_blocked");
      return INIT_FAILED;
   }
   if(!IsGoldSymbol())
   {
      Print("LAITH_BRIDGE_DISABLED gold_chart_required symbol=",_Symbol);
      return INIT_FAILED;
   }
   if(StringLen(BridgeBaseUrl)<8 || StringLen(BridgeClientToken)<16)
   {
      Print("LAITH_BRIDGE_DISABLED bridge_url_or_token_missing");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(MathAbs(DemoLots-0.01)>0.0000001)
   {
      Print("LAITH_BRIDGE_DISABLED demo_lot_must_be_0_01");
      return INIT_PARAMETERS_INCORRECT;
   }

   g_base_url=BridgeBaseUrl;
   while(StringLen(g_base_url)>0 && StringSubstr(g_base_url,StringLen(g_base_url)-1,1)=="/")
      g_base_url=StringSubstr(g_base_url,0,StringLen(g_base_url)-1);

   int seconds=PollSeconds;
   if(seconds<1) seconds=1;
   EventSetTimer(seconds);
   trade.SetExpertMagicNumber(MagicNumber);

   Print("LAITH_BRIDGE_READY demo=true symbol=",_Symbol,
         " local_kill_switch=",LocalKillSwitch,
         " url=",g_base_url);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PollBridge();
}

void OnTick()
{
   // Execution is timer-driven to avoid duplicate polling on fast ticks.
}
