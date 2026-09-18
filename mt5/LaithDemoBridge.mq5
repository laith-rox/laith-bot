// Laith MT5 Demo Bridge EA — DEMO ONLY.
// Attach to an XAUUSD chart in MT5 desktop. Live accounts are rejected.
// Network transport is intentionally not enabled until the endpoint/auth layer is approved.
#property strict
#include <Trade/Trade.mqh>
CTrade trade;

input double DemoLots = 0.01;
input long MagicNumber = 56002;

bool IsDemoAccount()
{
   return (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO);
}

bool HasOpenGoldPosition()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket>0 && PositionSelectByTicket(ticket))
      {
         string sym=PositionGetString(POSITION_SYMBOL);
         long magic=PositionGetInteger(POSITION_MAGIC);
         if(sym==_Symbol && magic==MagicNumber) return true;
      }
   }
   return false;
}

bool SafeInputs(string side,double sl,double tp)
{
   if(!IsDemoAccount()) return false;
   if(_Symbol!="XAUUSD" && StringFind(_Symbol,"XAUUSD")<0) return false;
   if(HasOpenGoldPosition()) return false;
   if(DemoLots<=0 || sl<=0 || tp<=0) return false;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return false;
   if(side=="BUY" && !(sl<tick.ask && tp>tick.ask)) return false;
   if(side=="SELL" && !(sl>tick.bid && tp<tick.bid)) return false;
   return true;
}

bool ExecuteDemo(string side,double sl,double tp,string id)
{
   if(!SafeInputs(side,sl,tp))
   {
      Print("LAITH_BRIDGE_REJECT id=",id);
      return false;
   }
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   bool ok=false;
   if(side=="BUY") ok=trade.Buy(DemoLots,_Symbol,0,sl,tp,"LaithDemo:"+id);
   else if(side=="SELL") ok=trade.Sell(DemoLots,_Symbol,0,sl,tp,"LaithDemo:"+id);
   Print("LAITH_BRIDGE_EXEC id=",id," ok=",ok," retcode=",trade.ResultRetcode());
   return ok;
}

int OnInit()
{
   if(!IsDemoAccount())
   {
      Print("LAITH_BRIDGE_DISABLED live account blocked");
      return INIT_FAILED;
   }
   trade.SetExpertMagicNumber(MagicNumber);
   Print("LAITH_BRIDGE_READY demo=true symbol=",_Symbol);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Deliberately idle: the authenticated command transport is the next layer.
}
