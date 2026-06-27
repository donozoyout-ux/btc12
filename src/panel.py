import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify
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
<title>TERMINAL.OS - Crypto Scanner</title>
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
.glow-green{box-shadow:0 0 10px rgba(16,185,129,0.15)}
.glow-red{box-shadow:0 0 10px rgba(244,63,94,0.15)}
.scrollbar::-webkit-scrollbar{width:4px}
.scrollbar::-webkit-scrollbar-track{background:#0e0e0f}
.scrollbar::-webkit-scrollbar-thumb{background:#45464b;border-radius:2px}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:0.4}}
.pulse-dot{animation:pulse-dot 1.5s infinite}
@keyframes scan-line{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.scan-line{animation:scan-line 2s ease-in-out infinite}
</style>
</head>
<body class="flex flex-col h-screen">
<!-- HEADER -->
<header class="bg-surface border-b border-border/30 flex items-center justify-between px-6 h-14 shrink-0">
<div class="flex items-center gap-4">
<h1 class="text-lg font-bold tracking-tight text-white">CRYPTO SCANNER</h1>
<div id="statusBadge" class="flex items-center gap-2 px-3 py-1 bg-green/10 border border-green/20 rounded text-xs font-bold text-green">
<span class="w-2 h-2 rounded-full bg-green pulse-dot"></span>
<span>ONLINE</span>
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
<!-- MAIN -->
<div class="flex flex-1 overflow-hidden">
<!-- CONTENT -->
<main class="flex-1 overflow-y-auto p-6 scrollbar">
<!-- STATS -->
<div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">TARAMA</div>
<div class="text-3xl font-mono font-bold text-white" id="sTotalScans">0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">SINYAL</div>
<div class="text-3xl font-mono font-bold text-accent" id="sSignalsSent">0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">COIN</div>
<div class="text-3xl font-mono font-bold text-white" id="sCoinsCount">0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">SON TARMA</div>
<div class="text-3xl font-mono font-bold text-green" id="sLastScan">--:--</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">FEAR/GREED</div>
<div class="text-3xl font-mono font-bold" id="sFearGreed">-</div>
</div>
</div>
<!-- TWO COL LAYOUT -->
<div class="grid grid-cols-12 gap-4" style="height:calc(100vh - 220px)">
<!-- LEFT: SCAN RESULTS -->
<div class="col-span-12 lg:col-span-8 flex flex-col">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Live Scan Results</h2>
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
<!-- RIGHT: SIGNALS -->
<div class="col-span-12 lg:col-span-4 flex flex-col">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Son Sinyaller</h2>
<span class="text-text3 text-xs" id="signalCount">0 sinyal</span>
</div>
<div class="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar pr-1" id="signalsList">
<div class="glass rounded-lg p-4 text-center text-text3 text-sm">Sinyal bekleniyor...</div>
</div>
<div class="glass rounded-lg p-3 mt-3 text-center border-dashed border-border/30">
<div class="text-[10px] font-bold tracking-widest text-text3" id="scanStatus">Bekleniyor...</div>
<div class="w-full bg-surface4 h-1 rounded-full mt-2 overflow-hidden">
<div class="bg-accent h-full w-0 transition-all duration-1000" id="progressBar"></div>
</div>
</div>
</div>
</div>
</main>
</div>
<script>
var currentFilter='all';
var progressW=0;
setInterval(()=>{progressW=(progressW+1.66)%100;document.getElementById('progressBar').style.width=progressW+'%'},1000);
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('tr-TR')},1000);

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
        // Status badge
        var badge=document.getElementById('statusBadge');
        if(d.running&&!d.paused){badge.innerHTML='<span class="w-2 h-2 rounded-full bg-green pulse-dot"></span><span>SCANNING</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-green/10 border border-green/20 rounded text-xs font-bold text-green'}
        else if(d.paused){badge.innerHTML='<span class="w-2 h-2 rounded-full bg-yellow-500 pulse-dot"></span><span>PAUSED</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs font-bold text-yellow-500'}
        else{badge.innerHTML='<span class="w-2 h-2 rounded-full bg-red"></span><span>STOPPED</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red'}

        document.getElementById('sTotalScans').textContent=d.total_scans.toLocaleString();
        document.getElementById('sSignalsSent').textContent=d.signals_sent;
        document.getElementById('sCoinsCount').textContent=d.symbols_count;
        document.getElementById('sLastScan').textContent=d.last_scan_time||'--:--';

        // Fear & Greed
        if(d.fear_greed){
            var fg=parseInt(d.fear_greed.value||50);
            var el=document.getElementById('sFearGreed');
            el.textContent=fg+' '+d.fear_greed.value_classification;
            el.style.color=fg<25?'#f43f5e':fg<45?'#f97316':fg<55?'#eab308':fg<75?'#84cc16':'#10b981';
        }

        // Scan results table
        var results=d.scan_results||[];
        if(currentFilter!=='ALL')results=results.filter(r=>r.action===currentFilter);
        results.sort((a,b)=>{
            if(a.action==='BUY'&&b.action!=='BUY')return -1;
            if(a.action==='SELL'&&b.action!=='SELL')return -1;
            return(b.confidence||0)-(a.confidence||0);
        });

        var tbody=document.getElementById('scanBody');
        if(results.length>0){
            var html='';
            results.forEach(r=>{
                var cls=r.action==='BUY'?'text-green':r.action==='SELL'?'text-red':'text-text3';
                var badge=r.action==='BUY'?'<span class="px-2 py-0.5 bg-green/10 text-green text-[10px] font-bold rounded border border-green/30">BUY</span>'
                    :r.action==='SELL'?'<span class="px-2 py-0.5 bg-red/10 text-red text-[10px] font-bold rounded border border-red/30">SELL</span>'
                    :'<span class="px-2 py-0.5 bg-surface4 text-text3 text-[10px] font-bold rounded">NEUTRAL</span>';
                var conf=r.confidence||0;
                var confColor=conf>0.7?'bg-green':conf>0.5?'bg-yellow-500':'bg-text3';
                var rsiColor=(r.rsi||50)<30?'text-green':(r.rsi||50)>70?'text-red':'text-text3';

                html+='<tr class="hover:bg-white/5 transition-colors"><td class="px-4 py-3 font-mono text-sm flex items-center gap-2"><div class="w-7 h-7 rounded-full bg-surface4 flex items-center justify-center text-[11px] font-bold">'+r.symbol.charAt(0)+'</div>'+r.symbol+'</td><td class="px-4 py-3">'+badge+'</td><td class="px-4 py-3"><div class="w-20 bg-surface4 h-1.5 rounded-full overflow-hidden"><div class="'+confColor+' h-full" style="width:'+conf*100+'%"></div></div><span class="font-mono text-[11px] mt-1 block">'+(conf*100).toFixed(0)+'%</span></td><td class="px-4 py-3 font-mono text-sm text-right">$'+(r.price||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:4})+'</td><td class="px-4 py-3 font-mono text-sm text-right '+rsiColor+'">'+(r.rsi||0).toFixed(1)+'</td><td class="px-4 py-3 font-mono text-sm text-right text-text3">'+(r.volume_ratio||0).toFixed(1)+'x</td></tr>';
            });
            tbody.innerHTML=html;
        }else{
            tbody.innerHTML='<tr><td colspan="6" class="px-4 py-12 text-center text-text3 italic">Tarama bekleniyor...</td></tr>';
        }

        // Recent signals
        var sigs=d.last_signals||{};
        var sigKeys=Object.keys(sigs);
        document.getElementById('signalCount').textContent=sigKeys.length+' sinyal';
        var sigList=document.getElementById('signalsList');
        if(sigKeys.length>0){
            var html='';
            sigKeys.slice(-8).reverse().forEach(coin=>{
                var s=sigs[coin];
                var color=s.action==='BUY'?'green':'red';
                var border=s.action==='BUY'?'border-green':'border-red';
                html+='<div class="glass rounded-lg p-3 border-l-4 '+border+' hover:translate-x-1 transition-transform cursor-pointer"><div class="flex justify-between items-start"><div><div class="font-bold text-'+color+'">'+coin+' - '+s.action+'</div><div class="text-xs text-text3 font-mono">$'+(s.price||0).toFixed(4)+' | Guven: '+(s.confidence*100).toFixed(0)+'%</div></div></div>'+(s.reason?'<div class="text-[10px] text-text3 mt-1 italic">'+s.reason.substring(0,60)+'</div>':'')+'</div>';
            });
            sigList.innerHTML=html;
        }

        document.getElementById('scanStatus').textContent=d.running?(d.paused?'DURAKLATILDI':'Tarama aktif - '+d.symbols_count+' coin'):clearInterval&&'Durdu';
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
    from src.coingecko import coingecko
    status = get_status()
    try:
        status["fear_greed"] = coingecko.get_fear_greed()
    except:
        status["fear_greed"] = {"value": "50", "value_classification": "Neutral"}
    status["logs"] = log_messages[-30:]
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
            log("Alpaca baglantisi basarisiz")
            return jsonify({"success": False, "message": "Alpaca baglantisi basarisiz"})

        bot_thread = threading.Thread(target=bot.run, daemon=True)
        bot_thread.start()

        time.sleep(2)
        if bot.running:
            log("Bot basarili!")
            return jsonify({"success": True, "message": "Bot baslatildi - " + str(len(settings.symbols)) + " coin taraniyor"})
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


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    log("Panel baslatildi")
    log(f"{len(settings.symbols)} coin taraniyor")
    print(f"[PANEL] http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
