// Laith MT5 REAL Bridge EA — STAGED / FAIL-CLOSED.
#property strict
#include <Trade/Trade.mqh>
CTrade trade;

input string BridgeBaseUrl = "https://laith-real-bridge-production.up.railway.app";
input string BridgeClientToken = "";
input int PollSeconds = 2;
input bool LocalKillSwitch = true;
input bool RealExecutionArmed = false;
input double RealLots = 0.0;
input double MaxRiskPerTradeUsd = 0.0;
input double MaxAggregateRiskUsd = 0.0;
input int MaxConcurrentPositions = 0;
input long MagicNumber = 56003;

string g_base_url="";

bool IsRealAccount(){ return AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL; }
bool IsGoldSymbol(){ return StringFind(_Symbol,"XAUUSD")>=0; }

int OwnedGoldCount()
{
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol &&
         StringFind(_Symbol,"XAUUSD")>=0 &&
         (long)PositionGetInteger(POSITION_MAGIC)==MagicNumber) count++;
   }
   return count;
}

double PositionRiskToStopUsd(ulong ticket)
{
   if(ticket==0 || !PositionSelectByTicket(ticket)) return 0.0;
   if(PositionGetString(POSITION_SYMBOL)!=_Symbol) return 0.0;
   if((long)PositionGetInteger(POSITION_MAGIC)!=MagicNumber) return 0.0;
   double volume=PositionGetDouble(POSITION_VOLUME);
   double open_price=PositionGetDouble(POSITION_PRICE_OPEN);
   double sl=PositionGetDouble(POSITION_SL);
   if(volume<=0 || open_price<=0 || sl<=0) return 0.0;
   long ptype=(long)PositionGetInteger(POSITION_TYPE);
   ENUM_ORDER_TYPE type=(ptype==POSITION_TYPE_BUY?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
   double pnl=0.0;
   if(!OrderCalcProfit(type,_Symbol,volume,open_price,sl,pnl)) return 0.0;
   return MathMax(0.0,-pnl);
}

double TotalOwnedRiskUsd()
{
   double total=0.0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket>0) total+=PositionRiskToStopUsd(ticket);
   }
   return total;
}

bool CalcPlannedLossUsd(string side,double volume,double sl,double &loss)
{
   loss=0.0;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return false;
   ENUM_ORDER_TYPE type;
   double open_price=0.0;
   if(side=="BUY"){ type=ORDER_TYPE_BUY; open_price=tick.ask; }
   else if(side=="SELL"){ type=ORDER_TYPE_SELL; open_price=tick.bid; }
   else return false;
   double pnl=0.0;
   if(!OrderCalcProfit(type,_Symbol,volume,open_price,sl,pnl)) return false;
   loss=MathMax(0.0,-pnl);
   return true;
}

bool FinancialConfigReady()
{
   return RealLots>0.0 && MaxRiskPerTradeUsd>0.0 &&
          MaxAggregateRiskUsd>0.0 && MaxConcurrentPositions>0;
}

bool SafeInputs(string side,double volume,double sl,double tp,string id)
{
   if(!IsRealAccount() || !IsGoldSymbol()) return false;
   if(LocalKillSwitch || !RealExecutionArmed) return false;
   if(!FinancialConfigReady()) return false;
   if(AccountInfoString(ACCOUNT_CURRENCY)!="USD") return false;
   if(MathAbs(volume-RealLots)>0.0000001) return false;
   if(OwnedGoldCount()>=MaxConcurrentPositions) return false;
   if(sl<=0 || tp<=0) return false;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return false;
   double min_distance=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point+2.0*_Point;
   if(side=="BUY" && !(sl<tick.bid-min_distance && tp>tick.bid+min_distance)) return false;
   if(side=="SELL" && !(sl>tick.ask+min_distance && tp<tick.ask-min_distance)) return false;
   if(side!="BUY" && side!="SELL") return false;

   double planned=0.0;
   if(!CalcPlannedLossUsd(side,volume,sl,planned) || planned<=0) return false;
   if(planned>MaxRiskPerTradeUsd+0.01) return false;
   if(TotalOwnedRiskUsd()+planned>MaxAggregateRiskUsd+0.01) return false;
   return true;
}

string ResultToString(char &result[])
{
   if(ArraySize(result)<=0) return "";
   return CharArrayToString(result,0,-1,CP_UTF8);
}

string TicketToString(ulong ticket){ return IntegerToString((long)ticket); }

bool CanReport()
{
   return StringLen(g_base_url)>=8 && StringLen(BridgeClientToken)>=16;
}

int HttpGet(string url,string &body)
{
   char data[]; char result[]; string response_headers;
   string headers="X-Client-Token: "+BridgeClientToken+"\r\n";
   ResetLastError();
   int code=WebRequest("GET",url,headers,5000,data,result,response_headers);
   body=ResultToString(result);
   if(code<0) Print("LAITH_REAL_HTTP_GET_ERROR err=",GetLastError());
   return code;
}

int HttpPostJson(string url,string json,string &body)
{
   char data[]; char result[]; string response_headers;
   StringToCharArray(json,data,0,WHOLE_ARRAY,CP_UTF8);
   if(ArraySize(data)>0) ArrayResize(data,ArraySize(data)-1);
   string headers="Content-Type: application/json\r\nX-Client-Token: "+BridgeClientToken+"\r\n";
   ResetLastError();
   int code=WebRequest("POST",url,headers,5000,data,result,response_headers);
   body=ResultToString(result);
   if(code<0) Print("LAITH_REAL_HTTP_POST_ERROR err=",GetLastError());
   return code;
}

bool VerifyCommand(string key,string ts,string symbol,string side,string volume,string sl,string tp,string sig)
{
   string url=g_base_url+"/verify?key="+key+"&ts="+ts+"&symbol="+symbol+
      "&side="+side+"&volume="+volume+"&sl="+sl+"&tp="+tp+"&sig="+sig;
   string body="";
   int code=HttpGet(url,body);
   return code==200 && StringFind(body,"OK")>=0;
}

void AckCommand(string key,bool ok,long retcode,ulong ticket)
{
   string body="";
   string json="{\"key\":\""+key+"\",\"ok\":"+(ok?"true":"false")+
      ",\"reason\":\"retcode_"+IntegerToString(retcode)+"\",\"ticket\":\""+
      TicketToString(ticket)+"\"}";
   HttpPostJson(g_base_url+"/ack",json,body);
}

string RatesJson(ENUM_TIMEFRAMES tf,int count)
{
   MqlRates rates[];
   int copied=CopyRates(_Symbol,tf,0,count,rates);
   if(copied<=0) return "[]";
   int offset=(int)(TimeCurrent()-TimeGMT());
   string out="[";
   for(int i=0;i<copied;i++)
   {
      if(i>0) out+=",";
      datetime utc_time=rates[i].time-offset;
      out+="{\"datetime\":\""+TimeToString(utc_time,TIME_DATE|TIME_MINUTES|TIME_SECONDS)+"\""+
           ",\"open\":"+DoubleToString(rates[i].open,_Digits)+
           ",\"high\":"+DoubleToString(rates[i].high,_Digits)+
           ",\"low\":"+DoubleToString(rates[i].low,_Digits)+
           ",\"close\":"+DoubleToString(rates[i].close,_Digits)+
           ",\"tick_volume\":"+IntegerToString((long)rates[i].tick_volume)+"}";
   }
   out+="]";
   return out;
}

void PostMarketState()
{
   string m5=RatesJson(PERIOD_M5,240);
   string m15=RatesJson(PERIOD_M15,100);
   string h1=RatesJson(PERIOD_H1,120);
   if(m5=="[]" || m15=="[]" || h1=="[]") return;
   string json="{\"mode\":\"REAL\",\"symbol\":\""+_Symbol+"\",\"m5\":"+m5+
      ",\"m15\":"+m15+",\"h1\":"+h1+"}";
   string body="";
   HttpPostJson(g_base_url+"/market",json,body);
}

void PostState()
{
   double price=0.0;
   MqlTick tick;
   if(SymbolInfoTick(_Symbol,tick)) price=(tick.bid+tick.ask)/2.0;
   int owned=OwnedGoldCount();
   string json="{\"mode\":\"REAL\",\"symbol\":\""+_Symbol+"\""+
      ",\"position_open\":"+(owned>0?"true":"false")+
      ",\"position_owned\":"+(owned>0?"true":"false")+
      ",\"owned_position_count\":"+IntegerToString(owned)+
      ",\"price\":\""+DoubleToString(price,_Digits)+"\""+
      ",\"total_position_risk_usd\":\""+DoubleToString(TotalOwnedRiskUsd(),2)+"\"}";
   string body="";
   HttpPostJson(g_base_url+"/state",json,body);
}

bool ExecuteReal(string side,double volume,double sl,double tp,string id)
{
   if(!SafeInputs(side,volume,sl,tp,id))
   {
      Print("LAITH_REAL_REJECT id=",id," reason=local_safety_gate");
      AckCommand(id,false,0,0);
      return false;
   }
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   bool ok=false;
   if(side=="BUY") ok=trade.Buy(volume,_Symbol,0,sl,tp,"LaithReal:"+id);
   else if(side=="SELL") ok=trade.Sell(volume,_Symbol,0,sl,tp,"LaithReal:"+id);
   long retcode=(long)trade.ResultRetcode();
   ulong ticket=trade.ResultOrder();
   Print("LAITH_REAL_EXEC id=",id," side=",side," ok=",ok," retcode=",retcode);
   AckCommand(id,ok,retcode,ticket);
   return ok;
}

void HandleOpenCommand(string body)
{
   string p[];
   int n=StringSplit(body,'|',p);
   if(n!=10 || p[0]!="CMD" || p[1]!="REAL")
   {
      Print("LAITH_REAL_BAD_COMMAND");
      return;
   }
   string key=p[2],ts=p[3],symbol=p[4],side=p[5],volume_s=p[6],sl_s=p[7],tp_s=p[8],sig=p[9];
   if(StringFind(symbol,"XAUUSD")<0) return;
   if(!VerifyCommand(key,ts,symbol,side,volume_s,sl_s,tp_s,sig))
   {
      Print("LAITH_REAL_REJECT id=",key," reason=verify_failed");
      return;
   }
   ExecuteReal(side,StringToDouble(volume_s),StringToDouble(sl_s),StringToDouble(tp_s),key);
}

void PollBridge()
{
   if(!IsRealAccount() || !IsGoldSymbol() || !CanReport()) return;
   PostState();
   static datetime last_market=0;
   datetime now=TimeCurrent();
   if(last_market==0 || now-last_market>=10)
   {
      PostMarketState();
      last_market=now;
   }
   if(LocalKillSwitch || !RealExecutionArmed || !FinancialConfigReady()) return;

   string body="";
   int code=HttpGet(g_base_url+"/next",body);
   if(code==423 || code==204) return;
   if(code!=200 || body=="NONE" || StringLen(body)<4) return;
   if(StringFind(body,"CMD|")==0) HandleOpenCommand(body);
}

int OnInit()
{
   if(!IsRealAccount())
   {
      Print("LAITH_REAL_STAGED real_account_required");
      return INIT_FAILED;
   }
   if(!IsGoldSymbol())
   {
      Print("LAITH_REAL_STAGED gold_chart_required symbol=",_Symbol);
      return INIT_FAILED;
   }
   g_base_url=BridgeBaseUrl;
   while(StringLen(g_base_url)>0 && StringSubstr(g_base_url,StringLen(g_base_url)-1,1)=="/")
      g_base_url=StringSubstr(g_base_url,0,StringLen(g_base_url)-1);

   int seconds=PollSeconds; if(seconds<1) seconds=1;
   EventSetTimer(seconds);
   trade.SetExpertMagicNumber(MagicNumber);
   Print("LAITH_REAL_STAGED_READY execution_armed=",RealExecutionArmed,
         " kill_switch=",LocalKillSwitch,
         " financial_config_ready=",FinancialConfigReady(),
         " token_configured=",(StringLen(BridgeClientToken)>=16));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){ EventKillTimer(); }
void OnTimer(){ PollBridge(); }
void OnTick(){}
