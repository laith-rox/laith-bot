#property strict
#property version   "1.00"
#property description "Laith V4 demo-first MT5 executor"

#include <Trade/Trade.mqh>

input string BridgeURL = "";
input string BridgeToken = "";
input string BrokerSymbol = "XAUUSD";
input int    PollSeconds = 3;
input double MaxEntryDeviationUSD = 1.00;
input double MaxSpreadUSD = 1.00;
input double MaxLots = 0.02;
input bool   AllowLiveTrading = false;
input long   MagicNumber = 460017;

CTrade Trade;
string LastExecutedOrder = "";

string Trim(string value)
{
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}

string JoinURL(string base,string path)
{
   base=Trim(base);
   while(StringLen(base)>0 && StringSubstr(base,StringLen(base)-1,1)=="/")
      base=StringSubstr(base,0,StringLen(base)-1);
   return base+path;
}

void LoadState()
{
   int h=FileOpen("LaithV4Executor.state",FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI);
   if(h==INVALID_HANDLE) return;
   if(!FileIsEnding(h)) LastExecutedOrder=Trim(FileReadString(h));
   FileClose(h);
}

void SaveState(string order_id)
{
   int h=FileOpen("LaithV4Executor.state",FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
   if(h==INVALID_HANDLE) return;
   FileWriteString(h,order_id);
   FileClose(h);
   LastExecutedOrder=order_id;
}

int HttpGet(string path,string &body)
{
   char data[];
   char result[];
   string response_headers="";
   string headers="X-Laith-Token: "+BridgeToken+"\r\nAccept: text/plain\r\n";
   ResetLastError();
   int code=WebRequest("GET",JoinURL(BridgeURL,path),headers,5000,data,result,response_headers);
   if(code<0)
   {
      Print("LaithV4 WebRequest GET failed error=",GetLastError(),". Add the bridge URL in Tools > Options > Expert Advisors > Allow WebRequest.");
      return code;
   }
   body=CharArrayToString(result,0,-1,CP_UTF8);
   return code;
}

int HttpPost(string path,string payload,string &body)
{
   char data[];
   int copied=StringToCharArray(payload,data,0,WHOLE_ARRAY,CP_UTF8);
   if(copied>0) ArrayResize(data,copied-1);
   char result[];
   string response_headers="";
   string headers="X-Laith-Token: "+BridgeToken+"\r\nContent-Type: text/plain; charset=utf-8\r\n";
   ResetLastError();
   int code=WebRequest("POST",JoinURL(BridgeURL,path),headers,5000,data,result,response_headers);
   if(code>=0) body=CharArrayToString(result,0,-1,CP_UTF8);
   return code;
}

void Ack(string order_id,string state,string ticket,string message)
{
   StringReplace(message,"|","/");
   StringReplace(message,"\r"," ");
   StringReplace(message,"\n"," ");
   string response="";
   int code=HttpPost("/v1/ack",order_id+"|"+state+"|"+ticket+"|"+message,response);
   if(code!=200)
      Print("LaithV4 ACK failed HTTP=",code," response=",response);
}

int OpenPositionsForExecutor()
{
   int count=0;
   for(int i=0;i<PositionsTotal();i++)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)==BrokerSymbol && PositionGetInteger(POSITION_MAGIC)==MagicNumber)
         count++;
   }
   return count;
}

bool TradingModeAllowed(string command_mode,string &reason)
{
   long account_mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(command_mode=="demo")
   {
      if(account_mode!=ACCOUNT_TRADE_MODE_DEMO)
      {
         reason="demo_command_requires_demo_account";
         return false;
      }
      return true;
   }
   if(command_mode=="live")
   {
      if(!AllowLiveTrading)
      {
         reason="live_trading_switch_is_off";
         return false;
      }
      if(account_mode!=ACCOUNT_TRADE_MODE_REAL)
      {
         reason="live_command_requires_real_account";
         return false;
      }
      return true;
   }
   reason="unknown_execution_mode";
   return false;
}

bool NormalizeRequestedLot(double requested,double &lot,string &reason)
{
   double min_lot=SymbolInfoDouble(BrokerSymbol,SYMBOL_VOLUME_MIN);
   double max_lot=SymbolInfoDouble(BrokerSymbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(BrokerSymbol,SYMBOL_VOLUME_STEP);
   if(requested<=0 || requested>MaxLots+1e-9)
   {
      reason="requested_lot_above_executor_limit";
      return false;
   }
   if(requested<min_lot-1e-9 || requested>max_lot+1e-9 || step<=0)
   {
      reason="requested_lot_not_supported_by_broker";
      return false;
   }
   double units=MathRound(requested/step);
   lot=units*step;
   int digits=2;
   if(step<0.01) digits=3;
   if(step<0.001) digits=4;
   lot=NormalizeDouble(lot,digits);
   if(MathAbs(lot-requested)>step*0.01)
   {
      reason="requested_lot_not_on_broker_step";
      return false;
   }
   return true;
}

void ProcessOrder(string line)
{
   line=Trim(line);
   if(line=="" || line=="NONE") return;

   string p[];
   ushort sep=(ushort)StringGetCharacter("|",0);
   int n=StringSplit(line,sep,p);
   if(n<10 || p[0]!="ORDER")
   {
      Print("LaithV4 malformed bridge response: ",line);
      return;
   }

   string order_id=Trim(p[1]);
   string mode=Trim(p[2]);
   string side=Trim(p[3]);
   string command_symbol=Trim(p[4]);
   double entry=StringToDouble(p[5]);
   double stop=StringToDouble(p[6]);
   double target=StringToDouble(p[7]);
   double requested_lot=StringToDouble(p[8]);
   long expires=(long)StringToDouble(p[9]);

   if(order_id==LastExecutedOrder)
   {
      Ack(order_id,"duplicate","","already_executed_locally");
      return;
   }

   string reason="";
   if(!TradingModeAllowed(mode,reason))
   {
      Ack(order_id,"rejected","",reason);
      return;
   }
   if(command_symbol!="XAUUSD")
   {
      Ack(order_id,"rejected","","unsupported_command_symbol");
      return;
   }
   if(expires>0 && TimeCurrent()>expires)
   {
      Ack(order_id,"rejected","","signal_expired");
      return;
   }
   if(side!="BUY" && side!="SELL")
   {
      Ack(order_id,"rejected","","invalid_side");
      return;
   }
   if(OpenPositionsForExecutor()>0)
   {
      Ack(order_id,"rejected","","executor_position_already_open");
      return;
   }
   if(!SymbolSelect(BrokerSymbol,true))
   {
      Ack(order_id,"rejected","","broker_symbol_unavailable");
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(BrokerSymbol,tick) || tick.ask<=0 || tick.bid<=0)
   {
      Ack(order_id,"rejected","","no_fresh_broker_tick");
      return;
   }
   double spread=tick.ask-tick.bid;
   if(spread>MaxSpreadUSD)
   {
      Ack(order_id,"rejected","","spread_above_limit");
      return;
   }
   double current=(side=="BUY" ? tick.ask : tick.bid);
   if(MathAbs(current-entry)>MaxEntryDeviationUSD)
   {
      Ack(order_id,"rejected","","entry_price_moved");
      return;
   }

   double lot=0;
   if(!NormalizeRequestedLot(requested_lot,lot,reason))
   {
      Ack(order_id,"rejected","",reason);
      return;
   }

   int digits=(int)SymbolInfoInteger(BrokerSymbol,SYMBOL_DIGITS);
   double point=SymbolInfoDouble(BrokerSymbol,SYMBOL_POINT);
   double min_distance=(double)SymbolInfoInteger(BrokerSymbol,SYMBOL_TRADE_STOPS_LEVEL)*point;
   stop=NormalizeDouble(stop,digits);
   target=NormalizeDouble(target,digits);
   if(side=="BUY" && !(stop<current-min_distance && target>current+min_distance))
   {
      Ack(order_id,"rejected","","buy_stop_or_target_invalid_at_broker_price");
      return;
   }
   if(side=="SELL" && !(target<current-min_distance && stop>current+min_distance))
   {
      Ack(order_id,"rejected","","sell_stop_or_target_invalid_at_broker_price");
      return;
   }

   Trade.SetExpertMagicNumber((ulong)MagicNumber);
   Trade.SetDeviationInPoints(20);
   bool ok=false;
   string comment="LaithV4";
   if(side=="BUY")
      ok=Trade.Buy(lot,BrokerSymbol,0.0,stop,target,comment);
   else
      ok=Trade.Sell(lot,BrokerSymbol,0.0,stop,target,comment);

   if(!ok)
   {
      Ack(order_id,"rejected","",Trade.ResultRetcodeDescription());
      Print("LaithV4 order rejected retcode=",Trade.ResultRetcode()," ",Trade.ResultRetcodeDescription());
      return;
   }

   ulong ticket=Trade.ResultOrder();
   SaveState(order_id); // persist before ACK so a network failure cannot duplicate the trade
   Ack(order_id,"opened",IntegerToString((long)ticket),Trade.ResultRetcodeDescription());
   Print("LaithV4 opened ",side," ",BrokerSymbol," lot=",DoubleToString(lot,2)," order=",ticket," id=",order_id);
}

void PollBridge()
{
   if(BridgeURL=="" || BridgeToken=="") return;
   string body="";
   int code=HttpGet("/v1/order.txt",body);
   if(code==200) ProcessOrder(body);
   else if(code>0) Print("LaithV4 bridge HTTP=",code," body=",body);
}

int OnInit()
{
   if(BridgeURL=="" || BridgeToken=="")
   {
      Print("LaithV4: BridgeURL and BridgeToken are required.");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL && !AllowLiveTrading)
   {
      Print("LaithV4: attached to a REAL account while AllowLiveTrading=false. Refusing to start.");
      return INIT_FAILED;
   }
   LoadState();
   Trade.SetExpertMagicNumber((ulong)MagicNumber);
   EventSetTimer((int)MathMax(1,PollSeconds));
   Print("LaithV4 executor started. account_mode=",AccountInfoInteger(ACCOUNT_TRADE_MODE)," live_switch=",AllowLiveTrading);
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
