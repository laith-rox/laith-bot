// Laith MT5 Demo Bridge EA — DEMO ONLY.
// Polls the isolated Laith Execution Bridge over HTTPS.
// Live accounts are rejected. Gold only. Fixed 0.01 lot. One open gold position max.
// Management v1.1: reports position state and supports verified MODIFY/CLOSE commands.
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

bool SelectOwnedGoldPosition(ulong &ticket)
{
   ticket=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong candidate=PositionGetTicket(i);
      if(candidate==0 || !PositionSelectByTicket(candidate))
         continue;

      string sym=PositionGetString(POSITION_SYMBOL);
      long magic=(long)PositionGetInteger(POSITION_MAGIC);
      if(sym==_Symbol && StringFind(sym,"XAUUSD")>=0 && magic==MagicNumber)
      {
         ticket=candidate;
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

string TicketToString(ulong ticket)
{
   return IntegerToString((long)ticket);
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

bool VerifyAction(string key,string ts,string symbol,string action,string sl,string tp,string sig)
{
   string url=g_base_url+
      "/verify-action?key="+key+
      "&ts="+ts+
      "&symbol="+symbol+
      "&action="+action+
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
               ",\"reason\":\"retcode_"+IntegerToString(retcode)+"\",\"ticket\":\""+
               TicketToString(ticket)+"\"}";
   int code=HttpPostJson(g_base_url+"/ack",json,body);
   Print("LAITH_BRIDGE_ACK key=",key," http=",code," body=",body);
}

void PostState()
{
   if(!IsDemoAccount() || !IsGoldSymbol())
      return;

   bool position_open=false;
   bool position_owned=false;
   ulong ticket=0;
   string side="";
   double volume=0.0;
   double open_price=0.0;
   double sl=0.0;
   double tp=0.0;
   double price=0.0;
   double profit=0.0;
   long magic=0;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong candidate=PositionGetTicket(i);
      if(candidate==0 || !PositionSelectByTicket(candidate))
         continue;

      string sym=PositionGetString(POSITION_SYMBOL);
      if(sym!=_Symbol || StringFind(sym,"XAUUSD")<0)
         continue;

      position_open=true;
      ticket=candidate;
      magic=(long)PositionGetInteger(POSITION_MAGIC);
      position_owned=(magic==MagicNumber);
      long ptype=(long)PositionGetInteger(POSITION_TYPE);
      side=(ptype==POSITION_TYPE_BUY ? "BUY" : "SELL");
      volume=PositionGetDouble(POSITION_VOLUME);
      open_price=PositionGetDouble(POSITION_PRICE_OPEN);
      sl=PositionGetDouble(POSITION_SL);
      tp=PositionGetDouble(POSITION_TP);
      price=PositionGetDouble(POSITION_PRICE_CURRENT);
      profit=PositionGetDouble(POSITION_PROFIT);
      break;
   }

   if(!position_open)
   {
      MqlTick tick;
      if(SymbolInfoTick(_Symbol,tick))
         price=(tick.bid+tick.ask)/2.0;
   }

   string json="{\"mode\":\"DEMO\",\"symbol\":\""+_Symbol+"\""+
               ",\"position_open\":"+(position_open?"true":"false")+
               ",\"position_owned\":"+(position_owned?"true":"false")+
               ",\"ticket\":\""+TicketToString(ticket)+"\""+
               ",\"side\":\""+side+"\""+
               ",\"volume\":\""+DoubleToString(volume,2)+"\""+
               ",\"open_price\":\""+DoubleToString(open_price,_Digits)+"\""+
               ",\"sl\":\""+DoubleToString(sl,_Digits)+"\""+
               ",\"tp\":\""+DoubleToString(tp,_Digits)+"\""+
               ",\"price\":\""+DoubleToString(price,_Digits)+"\""+
               ",\"profit\":\""+DoubleToString(profit,2)+"\""+
               ",\"magic\":\""+IntegerToString(magic)+"\"}";

   string body="";
   int code=HttpPostJson(g_base_url+"/state",json,body);
   if(code!=200)
      Print("LAITH_BRIDGE_STATE_ERROR http=",code," body=",body);
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

bool ModifyOwnedPosition(double sl,double tp,string id)
{
   if(!IsDemoAccount() || !IsGoldSymbol() || LocalKillSwitch || sl<=0 || tp<=0)
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",id," action=MODIFY reason=local_safety_gate");
      AckCommand(id,false,0,0);
      return false;
   }

   ulong ticket=0;
   if(!SelectOwnedGoldPosition(ticket))
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",id," action=MODIFY reason=no_owned_position");
      AckCommand(id,false,0,0);
      return false;
   }

   long ptype=(long)PositionGetInteger(POSITION_TYPE);
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
   {
      AckCommand(id,false,0,ticket);
      return false;
   }

   if(ptype==POSITION_TYPE_BUY && !(sl<tick.bid && tp>tick.bid))
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",id," action=MODIFY reason=bad_levels_buy");
      AckCommand(id,false,0,ticket);
      return false;
   }
   if(ptype==POSITION_TYPE_SELL && !(sl>tick.ask && tp<tick.ask))
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",id," action=MODIFY reason=bad_levels_sell");
      AckCommand(id,false,0,ticket);
      return false;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   bool ok=trade.PositionModify(ticket,sl,tp);
   long retcode=(long)trade.ResultRetcode();
   Print("LAITH_BRIDGE_MANAGE id=",id," action=MODIFY ok=",ok,
         " retcode=",retcode," ticket=",ticket," sl=",sl," tp=",tp);
   AckCommand(id,ok,retcode,ticket);
   return ok;
}

bool CloseOwnedPosition(string id)
{
   if(!IsDemoAccount() || !IsGoldSymbol() || LocalKillSwitch)
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",id," action=CLOSE reason=local_safety_gate");
      AckCommand(id,false,0,0);
      return false;
   }

   ulong ticket=0;
   if(!SelectOwnedGoldPosition(ticket))
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",id," action=CLOSE reason=no_owned_position");
      AckCommand(id,false,0,0);
      return false;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   bool ok=trade.PositionClose(ticket);
   long retcode=(long)trade.ResultRetcode();
   Print("LAITH_BRIDGE_MANAGE id=",id," action=CLOSE ok=",ok,
         " retcode=",retcode," ticket=",ticket);
   AckCommand(id,ok,retcode,ticket);
   return ok;
}

void HandleOpenCommand(string body)
{
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

void HandleActionCommand(string body)
{
   string parts[];
   int n=StringSplit(body,'|',parts);
   // ACT|DEMO|ACTION|key|ts|symbol|action|sl|tp|sig
   if(n!=10 || parts[0]!="ACT" || parts[1]!="DEMO" || parts[2]!="ACTION")
   {
      Print("LAITH_BRIDGE_BAD_ACTION body=",body);
      return;
   }

   string key=parts[3];
   string ts=parts[4];
   string symbol=parts[5];
   string action=parts[6];
   string sl_s=parts[7];
   string tp_s=parts[8];
   string sig=parts[9];

   if(StringFind(symbol,"XAUUSD")<0)
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",key," reason=symbol");
      return;
   }

   if(!VerifyAction(key,ts,symbol,action,sl_s,tp_s,sig))
   {
      Print("LAITH_BRIDGE_MANAGE_REJECT id=",key," reason=verify_failed");
      return;
   }

   if(action=="MODIFY")
   {
      ModifyOwnedPosition(StringToDouble(sl_s),StringToDouble(tp_s),key);
      return;
   }
   if(action=="CLOSE")
   {
      CloseOwnedPosition(key);
      return;
   }

   Print("LAITH_BRIDGE_MANAGE_REJECT id=",key," reason=unknown_action");
   AckCommand(key,false,0,0);
}

void PollBridge()
{
   PostState();

   if(LocalKillSwitch)
      return;

   string body="";
   int code=HttpGet(g_base_url+"/next",body);
   if(code==423 || code==204) return;
   if(code!=200) return;
   if(body=="NONE" || StringLen(body)<4) return;

   if(StringFind(body,"CMD|")==0)
   {
      HandleOpenCommand(body);
      return;
   }
   if(StringFind(body,"ACT|")==0)
   {
      HandleActionCommand(body);
      return;
   }

   Print("LAITH_BRIDGE_BAD_WIRE body=",body);
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
         " management=true state_report=true url=",g_base_url);
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
   // Execution and management are timer-driven to avoid duplicate polling on fast ticks.
}
