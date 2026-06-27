import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify, request
import threading
import time
from datetime import datetime
from src.config import settings
from src.main import CryptoBot, start_bot, stop_bot, pause_bot, get_status

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crypto-scanner-terminal'

bot = None
bot_thread = None
log_messages = []


def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    entry = f"[{timestamp}] {msg}"
    log_messages.append(entry)
    if len(log_messages) > 200:
        log_messages.pop(0)
    print(entry)


HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRYPTO SCANNER</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<script>
tailwind.config={darkMode:"class",theme:{extend:{colors:{bg:"#0a0e17",surface:"#131314",surface2:"#1c2127",surface3:"#201f20",surface4:"#2a2a2b",surface5:"#353435",border:"#45464b",text:"#e5e2e2",text2:"#c6c6cc",text3:"#909096",green:"#10b981",red:"#f43f5e",accent:"#3b82f6"},fontFamily:{body:["Inter"],mono:["JetBrains Mono"]}}}}
</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0a0e17;color:#e5e2e2;overflow:hidden;height:100vh}
.glass{background:rgba(28,33,39,0.8);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.05)}
.scrollbar::-webkit-scrollbar{width:4px}
.scrollbar::-webkit-scrollbar-track{background:#0e0e0f}
.scrollbar::-webkit-scrollbar-thumb{background:#45464b;border-radius:2px}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:0.4}}
.pulse-dot{animation:pulse-dot 1.5s infinite}
.sell-cb{width:16px;height:16px;accent-color:#f43f5e;cursor:pointer}
.sell-btn{transition:all .15s}
.sell-btn:hover{transform:scale(1.05)}
.sell-btn:active{transform:scale(0.95)}
.tab-active{border-bottom:2px solid #3b82f6;color:#fff}
.tab-inactive{border-bottom:2px solid transparent;color:#909096}
</style>
</head>
<body class="flex flex-col h-screen">
<header class="bg-surface border-b border-border/30 flex items-center justify-between px-6 h-14 shrink-0">
<div class="flex items-center gap-4">
<h1 class="text-lg font-bold tracking-tight text-white">CRYPTO SCANNER</h1>
<div id="statusBadge" class="flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red">
<span class="w-2 h-2 rounded-full bg-red"></span>
<span>STOPPED</span>
</div>
</div>
<div class="flex items-center gap-3">
<button onclick="startBot()" id="btnStart" class="px-4 py-1.5 bg-green hover:bg-green/80 text-black text-xs font-bold rounded flex items-center gap-1 transition-all active:scale-95">
<span class="material-symbols-outlined text-sm">play_arrow</span> START
</button>
<button onclick="stopBot()" class="px-4 py-1.5 bg-red hover:bg-red/80 text-white text-xs font-bold rounded flex items-center gap-1 transition-all active:scale-95">
<span class="material-symbols-outlined text-sm">stop</span> STOP
</button>
<button onclick="pauseBot()" id="btnPause" class="px-4 py-1.5 bg-surface4 hover:bg-surface5 text-text text-xs font-bold rounded flex items-center gap-1 transition-all active:scale-95">
<span class="material-symbols-outlined text-sm">pause</span> PAUSE
</button>
<button onclick="refresh()" class="px-4 py-1.5 bg-surface4 hover:bg-surface5 text-text text-xs font-bold rounded flex items-center gap-1 transition-all active:scale-95">
<span class="material-symbols-outlined text-sm">refresh</span>
</button>
<div class="w-px h-6 bg-border/30 mx-1"></div>
<span class="text-text3 text-xs font-mono" id="clock"></span>
</div>
</header>
<div class="flex flex-1 overflow-hidden">
<main class="flex-1 overflow-y-auto p-6 scrollbar">
<div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">PORTFOY</div>
<div class="text-2xl font-mono font-bold text-white" id="sPortfolio">$0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">NAKIT</div>
<div class="text-2xl font-mono font-bold text-white" id="sCash">$0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">ACIK K/Z</div>
<div class="text-2xl font-mono font-bold" id="sPnl">$0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">TARAMA</div>
<div class="text-2xl font-mono font-bold text-white" id="sTotalScans">0</div>
</div>
</div>

<div class="grid grid-cols-12 gap-4" style="height:calc(100vh - 200px)">
<div class="col-span-12 lg:col-span-8 flex flex-col">
<div class="flex items-center gap-4 mb-3">
<button onclick="switchTab('scan')" id="tabScan" class="text-xs font-bold pb-1 tab-active cursor-pointer">TARAMA</button>
<button onclick="switchTab('positions')" id="tabPos" class="text-xs font-bold pb-1 tab-inactive cursor-pointer">POZISYONLAR</button>
</div>

<div id="scanPanel" class="flex flex-col flex-1">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Tarama Sonuclari</h2>
<div class="flex gap-2">
<button onclick="filterAction('all')" class="filter-btn px-2 py-0.5 text-[10px] font-bold border border-border/30 rounded text-text3 hover:text-white">ALL</button>
<button onclick="filterAction('BUY')" class="filter-btn px-2 py-0.5 text-[10px] font-bold border border-green/30 rounded text-green hover:bg-green/10">BUY</button>
<button onclick="filterAction('SELL')" class="filter-btn px-2 py-0.5 text-[10px] font-bold border border-red/30 rounded text-red hover:bg-red/10">SELL</button>
</div>
</div>
<div class="glass rounded-lg overflow-hidden flex-1">
<table class="w-full text-left">
<thead class="bg-surface3/50 border-b border-border/20">
<tr>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">COIN</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">DURUM</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">GUVEN</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">FIYAT</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">RSI</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">HACIM</th>
</tr>
</thead>
<tbody id="scanBody" class="divide-y divide-border/10 scrollbar overflow-y-auto">
<tr><td colspan="6" class="px-4 py-12 text-center text-text3 italic">Tarama bekleniyor...</td></tr>
</tbody>
</table>
</div>
</div>

<div id="posPanel" class="flex flex-col flex-1 hidden">
<div class="flex items-center justify-between mb-3">
<div class="flex items-center gap-3">
<h2 class="text-sm font-bold text-white">Pozisyonlar</h2>
<span class="text-text3 text-xs" id="posCount">0</span>
</div>
<div class="flex gap-2">
<button onclick="sellSelected()" class="px-3 py-1 bg-red hover:bg-red/80 text-white text-[10px] font-bold rounded transition-all active:scale-95">SECILENLERI SAT</button>
<button onclick="sellAll()" class="px-3 py-1 bg-red hover:bg-red/80 text-white text-[10px] font-bold rounded transition-all active:scale-95">HEPSINI SAT</button>
</div>
</div>
<div class="glass rounded-lg overflow-hidden flex-1">
<table class="w-full text-left">
<thead class="bg-surface3/50 border-b border-border/20">
<tr>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 w-10"><input type="checkbox" id="selectAllCb" class="sell-cb" onchange="toggleAll(this)"></th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">COIN</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">MIKTAR</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">GIRIS</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">DEGER</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">K/Z</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 w-16"></th>
</tr>
</thead>
<tbody id="posBody" class="divide-y divide-border/10 scrollbar overflow-y-auto">
<tr><td colspan="7" class="px-4 py-12 text-center text-text3 italic">Pozisyon yok</td></tr>
</tbody>
</table>
</div>
</div>
</div>

<div class="col-span-12 lg:col-span-4 flex flex-col">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Bekleyen Onaylar</h2>
</div>
<div class="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar pr-1" id="pendingList">
<div class="glass rounded-lg p-4 text-center text-text3 text-sm">Bekleyen islem yok</div>
</div>
<div class="glass rounded-lg p-3 mt-3 text-center border-dashed border-border/30">
<div class="text-[10px] font-bold tracking-widest text-text3" id="scanStatus">Durdu</div>
</div>
</div>
</div>
</main>
</div>
<script>
var currentFilter='all';
var currentTab='scan';
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('tr-TR')},1000);

function switchTab(t){
    currentTab=t;
    document.getElementById('tabScan').className=t==='scan'?'text-xs font-bold pb-1 tab-active cursor-pointer':'text-xs font-bold pb-1 tab-inactive cursor-pointer';
    document.getElementById('tabPos').className=t==='positions'?'text-xs font-bold pb-1 tab-active cursor-pointer':'text-xs font-bold pb-1 tab-inactive cursor-pointer';
    document.getElementById('scanPanel').className=t==='scan'?'flex flex-col flex-1':'flex flex-col flex-1 hidden';
    document.getElementById('posPanel').className=t==='positions'?'flex flex-col flex-1':'flex flex-col flex-1 hidden';
}

function startBot(){
    document.getElementById('btnStart').disabled=true;
    fetch('/api/start',{method:'POST'}).then(r=>r.json()).then(d=>{
        toast(d.message||'Baslatildi','success');
        setTimeout(refresh,2000);
        document.getElementById('btnStart').disabled=false;
    }).catch(e=>{toast('Hata: '+e,'error');document.getElementById('btnStart').disabled=false});
}
function stopBot(){fetch('/api/stop',{method:'POST'}).then(r=>r.json()).then(d=>{toast('Durdu','info');setTimeout(refresh,1000)})}
function pauseBot(){fetch('/api/pause',{method:'POST'}).then(r=>r.json()).then(d=>{toast(d.paused?'Duraklatildi':'Devam','info');setTimeout(refresh,1000)})}
function refresh(){updateStatus()}
function filterAction(f){currentFilter=f;updateStatus()}

function sellCoin(sym){
    if(!confirm(sym+' satilsin mi?'))return;
    fetch('/api/sell',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:sym})})
    .then(r=>r.json()).then(d=>{toast(d.message,d.success?'success':'error');setTimeout(refresh,2000)});
}

function sellSelected(){
    var cbs=document.querySelectorAll('.pos-cb:checked');
    var syms=[];cbs.forEach(cb=>syms.push(cb.dataset.sym));
    if(syms.length===0){toast('Coin secin','error');return;}
    if(!confirm(syms.length+' coin satilsin mi?'))return;
    fetch('/api/sell-multi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbols:syms})})
    .then(r=>r.json()).then(d=>{toast(d.message,d.success?'success':'error');setTimeout(refresh,2000)});
}

function sellAll(){
    if(!confirm('TUM POZISYONLAR SATILSIN MI?'))return;
    fetch('/api/sell-all',{method:'POST'}).then(r=>r.json()).then(d=>{toast(d.message,d.success?'success':'error');setTimeout(refresh,2000)});
}

function toggleAll(el){
    document.querySelectorAll('.pos-cb').forEach(cb=>cb.checked=el.checked);
}

function toast(msg,type){
    var t=document.createElement('div');
    t.className='fixed top-20 right-6 px-4 py-2 rounded text-sm font-bold z-50 transition-all';
    if(type==='success')t.className+=' bg-green text-black';
    else if(type==='error')t.className+=' bg-red text-white';
    else t.className+=' bg-surface4 text-white';
    t.textContent=msg;document.body.appendChild(t);
    setTimeout(()=>t.remove(),3000);
}

function updateStatus(){
    fetch('/api/status').then(r=>r.json()).then(d=>{
        var badge=document.getElementById('statusBadge');
        if(d.running&&!d.paused){badge.innerHTML='<span class="w-2 h-2 rounded-full bg-green pulse-dot"></span><span>SCANNING</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-green/10 border border-green/20 rounded text-xs font-bold text-green'}
        else if(d.paused){badge.innerHTML='<span class="w-2 h-2 rounded-full bg-yellow-500 pulse-dot"></span><span>PAUSED</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs font-bold text-yellow-500'}
        else{badge.innerHTML='<span class="w-2 h-2 rounded-full bg-red"></span><span>STOPPED</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red'}

        document.getElementById('sTotalScans').textContent=d.total_scans.toLocaleString();

        if(d.balance){
            document.getElementById('sPortfolio').textContent='$'+parseFloat(d.balance.portfolio_value||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
            document.getElementById('sCash').textContent='$'+parseFloat(d.balance.cash||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
            var pnl=parseFloat(d.balance.unrealized_pl||0);
            var el=document.getElementById('sPnl');
            el.textContent='$'+(pnl>=0?'+':'')+pnl.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
            el.className='text-2xl font-mono font-bold '+(pnl>=0?'text-green':'text-red');
        }

        var results=d.scan_results||[];
        if(currentFilter!=='ALL')results=results.filter(r=>r.action===currentFilter);
        results.sort((a,b)=>(b.confidence||0)-(a.confidence||0));
        var tbody=document.getElementById('scanBody');
        if(results.length>0){
            var html='';
            results.forEach(r=>{
                var badge=r.action==='BUY'?'<span class="px-2 py-0.5 bg-green/10 text-green text-[10px] font-bold rounded border border-green/30">BUY</span>'
                    :r.action==='SELL'?'<span class="px-2 py-0.5 bg-red/10 text-red text-[10px] font-bold rounded border border-red/30">SELL</span>'
                    :'<span class="px-2 py-0.5 bg-surface4 text-text3 text-[10px] font-bold rounded">HOLD</span>';
                var conf=r.confidence||0;
                var confColor=conf>0.7?'bg-green':conf>0.5?'bg-yellow-500':'bg-text3';
                var rsiColor=(r.rsi||50)<30?'text-green':(r.rsi||50)>70?'text-red':'text-text3';
                html+='<tr class="hover:bg-white/5 transition-colors"><td class="px-4 py-3 font-mono text-sm flex items-center gap-2"><div class="w-7 h-7 rounded-full bg-surface4 flex items-center justify-center text-[11px] font-bold">'+r.symbol.charAt(0)+'</div>'+r.symbol+'</td><td class="px-4 py-3">'+badge+'</td><td class="px-4 py-3"><div class="w-20 bg-surface4 h-1.5 rounded-full overflow-hidden"><div class="'+confColor+' h-full" style="width:'+conf*100+'%"></div></div><span class="font-mono text-[11px] mt-1 block">'+(conf*100).toFixed(0)+'%</span></td><td class="px-4 py-3 font-mono text-sm text-right">$'+(r.price||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:4})+'</td><td class="px-4 py-3 font-mono text-sm text-right '+rsiColor+'">'+(r.rsi||0).toFixed(1)+'</td><td class="px-4 py-3 font-mono text-sm text-right text-text3">'+(r.volume_ratio||0).toFixed(1)+'x</td></tr>';
            });
            tbody.innerHTML=html;
        }else{
            tbody.innerHTML='<tr><td colspan="6" class="px-4 py-12 text-center text-text3 italic">Tarama bekleniyor...</td></tr>';
        }

        var positions=d.positions||[];
        document.getElementById('posCount').textContent=positions.length+' coin';
        var posBody=document.getElementById('posBody');
        if(positions.length>0){
            var html='';
            var totalPnl=0;
            positions.forEach(p=>{
                var pl=p.unrealized_pl||0;
                totalPnl+=pl;
                var entry=p.avg_entry_price||0;
                var mv=p.market_value||0;
                var yuzde=entry>0?((mv-entry*p.qty)/(entry*p.qty)*100):0;
                var plColor=pl>=0?'text-green':'text-red';
                html+='<tr class="hover:bg-white/5 transition-colors">';
                html+='<td class="px-4 py-3"><input type="checkbox" class="sell-cb pos-cb" data-sym="'+p.symbol+'"></td>';
                html+='<td class="px-4 py-3 font-mono text-sm font-bold">'+p.symbol+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">'+p.qty.toFixed(6)+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">$'+entry.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:4})+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">$'+mv.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right '+plColor+'">$'+pl.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+' ('+yuzde.toFixed(1)+'%)</td>';
                html+='<td class="px-4 py-3 text-right"><button onclick="sellCoin(\\''+p.symbol+'\\')" class="sell-btn px-3 py-1 bg-red/20 hover:bg-red text-red hover:text-white text-[10px] font-bold rounded border border-red/30">SAT</button></td>';
                html+='</tr>';
            });
            posBody.innerHTML=html;
        }else{
            posBody.innerHTML='<tr><td colspan="7" class="px-4 py-12 text-center text-text3 italic">Pozisyon yok</td></tr>';
        }

        var pending=d.pending_trades||[];
        var pendingSells=d.pending_sells||[];
        var pendingList=document.getElementById('pendingList');
        if(pending.length>0||pendingSells.length>0){
            var html='';
            pending.forEach(t=>{
                html+='<div class="glass rounded-lg p-3 border-l-4 border-green"><div class="flex justify-between items-start"><div><div class="font-bold text-green">'+t.symbol+' - ALIS</div><div class="text-xs text-text3 font-mono">$'+t.price.toFixed(4)+' | Guven: '+(t.confidence*100).toFixed(0)+'%</div></div></div></div>';
            });
            pendingSells.forEach(s=>{
                html+='<div class="glass rounded-lg p-3 border-l-4 border-red"><div class="flex justify-between items-start"><div><div class="font-bold text-red">'+s.symbol+' - SATIS</div><div class="text-xs text-text3 font-mono">$'+s.price.toFixed(4)+' | K/Z: $'+(s.unrealized_pl||0).toFixed(2)+'</div></div></div></div>';
            });
            pendingList.innerHTML=html;
        }else{
            pendingList.innerHTML='<div class="glass rounded-lg p-4 text-center text-text3 text-sm">Bekleyen islem yok</div>';
        }

        document.getElementById('scanStatus').textContent=d.running?(d.paused?'DURAKLATILDI':'Tarama aktif'):clearInterval&&'Durdu';
    }).catch(e=>console.log('Status error:',e));
}

refresh();
setInterval(refresh,3000);
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/status')
def api_status():
    global bot
    status = get_status()

    try:
        if bot and bot.running:
            acc = bot.client.get_account()
            positions = bot.client.get_positions()
            status["balance"] = {
                "portfolio_value": float(acc.portfolio_value),
                "cash": float(acc.cash),
                "unrealized_pl": sum(p.get("unrealized_pl", 0) for p in positions)
            }
            status["positions"] = positions
        else:
            status["balance"] = {"portfolio_value": 0, "cash": 0, "unrealized_pl": 0}
            status["positions"] = []
    except Exception as e:
        status["balance"] = {"portfolio_value": 0, "cash": 0, "unrealized_pl": 0}
        status["positions"] = []

    from src.telegram_bot import telegram_handler
    if telegram_handler:
        status["pending_trades"] = list(telegram_handler.pending_trades.values())
        status["pending_sells"] = list(telegram_handler.pending_sells.values())
    else:
        status["pending_trades"] = []
        status["pending_sells"] = []

    return jsonify(status)


@app.route('/api/start', methods=['POST'])
def api_start():
    global bot, bot_thread
    try:
        if bot and bot.running:
            return jsonify({"success": False, "message": "Bot zaten calisiyor"})

        log("Bot baslatiliyor...")
        bot = CryptoBot()

        if not bot.check_connection():
            return jsonify({"success": False, "message": "Alpaca baglantisi basarisiz"})

        bot_thread = threading.Thread(target=bot.run, daemon=True)
        bot_thread.start()

        time.sleep(2)
        if bot.running:
            log("Bot basarili!")
            return jsonify({"success": True, "message": "Bot baslatildi - " + str(len(settings.symbols)) + " coin"})
        else:
            return jsonify({"success": False, "message": "Bot baslatilamadi"})
    except Exception as e:
        log(f"Hata: {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    global bot
    try:
        if bot:
            bot.running = False
            log("Bot durduruldu")
            return jsonify({"success": True})
        return jsonify({"success": False})
    except:
        return jsonify({"success": False})


@app.route('/api/pause', methods=['POST'])
def api_pause():
    global bot
    try:
        if bot:
            bot.paused = not bot.paused
            state = "duraklatildi" if bot.paused else "devam ediyor"
            log(f"Bot {state}")
            return jsonify({"success": True, "paused": bot.paused})
        return jsonify({"success": False})
    except:
        return jsonify({"success": False})


@app.route('/api/sell', methods=['POST'])
def api_sell():
    global bot
    try:
        data = request.get_json()
        symbol = data.get("symbol", "")
        if not symbol:
            return jsonify({"success": False, "message": "Symbol gerekli"})

        if not bot or not bot.running:
            return jsonify({"success": False, "message": "Bot calismiyor"})

        position = bot.client.get_position(symbol)
        if not position:
            return jsonify({"success": False, "message": f"{symbol} pozisyon yok"})

        from alpaca.trading.enums import OrderSide
        qty = position["qty"]
        bot.client.cancel_all_orders()
        bot.client.place_market_order(OrderSide.SELL, qty, symbol)

        from src.telegram_bot import telegram_handler
        if telegram_handler:
            telegram_handler.send_message(f"<b>PANEL SATIS</b>  <code>{symbol}</code>\nMiktar: <code>{qty:.6f}</code>")

        log(f"Panel satis: {symbol} {qty}")
        return jsonify({"success": True, "message": f"{symbol} satildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/sell-multi', methods=['POST'])
def api_sell_multi():
    global bot
    try:
        data = request.get_json()
        symbols = data.get("symbols", [])
        if not symbols:
            return jsonify({"success": False, "message": "Coin secin"})

        if not bot or not bot.running:
            return jsonify({"success": False, "message": "Bot calismiyor"})

        from alpaca.trading.enums import OrderSide
        sold = []
        for sym in symbols:
            try:
                position = bot.client.get_position(sym)
                if position:
                    bot.client.cancel_all_orders()
                    bot.client.place_market_order(OrderSide.SELL, position["qty"], sym)
                    sold.append(sym)
            except:
                pass

        from src.telegram_bot import telegram_handler
        if telegram_handler and sold:
            telegram_handler.send_message(f"<b>PANEL TOPLU SATIS</b>\n{len(sold)} coin satildi: {', '.join(sold)}")

        log(f"Panel toplu satis: {len(sold)} coin")
        return jsonify({"success": True, "message": f"{len(sold)} coin satildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/sell-all', methods=['POST'])
def api_sell_all():
    global bot
    try:
        if not bot or not bot.running:
            return jsonify({"success": False, "message": "Bot calismiyor"})

        positions = bot.client.get_positions()
        if not positions:
            return jsonify({"success": False, "message": "Pozisyon yok"})

        from alpaca.trading.enums import OrderSide
        sold = []
        for p in positions:
            try:
                bot.client.cancel_all_orders()
                bot.client.place_market_order(OrderSide.SELL, p["qty"], p["symbol"])
                sold.append(p["symbol"])
            except:
                pass

        from src.telegram_bot import telegram_handler
        if telegram_handler and sold:
            telegram_handler.send_message(f"<b>PANEL HEPSINI SAT</b>\n{len(sold)} coin satildi")

        log(f"Panel hepsini sat: {len(sold)} coin")
        return jsonify({"success": True, "message": f"{len(sold)} coin satildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    log("Panel baslatildi")
    log(f"{len(settings.symbols)} coin taraniyor")

    from src.telegram_bot import init_telegram
    init_telegram()
    log("Telegram polling baslatildi")

    print(f"[PANEL] http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
