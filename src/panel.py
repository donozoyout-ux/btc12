import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify
import threading
from datetime import datetime
from src.bot import bot, setup_telegram
from src.trader import trader
from src.config import settings
from src.telegram import tg
from src.quant_agent import quant_agent
from src.database import db

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BTC AI BOT</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0a0e17;color:#e5e2e2;overflow:hidden;height:100vh}
.glass{background:rgba(28,33,39,0.8);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.05)}
.scrollbar::-webkit-scrollbar{width:4px}
.scrollbar::-webkit-scrollbar-track{background:#0e0e0f}
.scrollbar::-webkit-scrollbar-thumb{background:#45464b;border-radius:2px}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:0.4}}
.pulse-dot{animation:pulse-dot 1.5s infinite}
.btn{transition:all .15s}.btn:hover{transform:scale(1.03)}.btn:active{transform:scale(0.97)}
</style>
</head>
<body class="flex flex-col h-screen">
<header class="bg-[#131314] border-b border-[#45464b]/30 flex items-center justify-between px-6 h-14 shrink-0">
<div class="flex items-center gap-4">
<h1 class="text-lg font-bold tracking-tight text-white">BTC AI BOT</h1>
<div id="statusBadge" class="flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red">
<span class="w-2 h-2 rounded-full bg-red"></span><span>STOPPED</span>
</div>
</div>
<div class="flex items-center gap-3">
<button onclick="startBot()" class="btn px-4 py-1.5 bg-green hover:bg-green/80 text-black text-xs font-bold rounded">START</button>
<button onclick="stopBot()" class="btn px-4 py-1.5 bg-red hover:bg-red/80 text-white text-xs font-bold rounded">STOP</button>
<button onclick="scanNow()" class="btn px-4 py-1.5 bg-blue-500 hover:bg-blue-500/80 text-white text-xs font-bold rounded">SCAN</button>
<span class="text-text3 text-xs font-mono" id="clock"></span>
</div>
</header>
<div class="flex-1 overflow-y-auto p-6 scrollbar">
<div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
<div class="glass rounded-lg p-4 text-center">
<div class="text-[#909096] text-[10px] font-bold tracking-widest mb-1">PORTFOY</div>
<div class="text-2xl font-mono font-bold text-white" id="sPortfolio">$0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-[#909096] text-[10px] font-bold tracking-widest mb-1">NAKIT</div>
<div class="text-2xl font-mono font-bold text-white" id="sCash">$0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-[#909096] text-[10px] font-bold tracking-widest mb-1">K/Z</div>
<div class="text-2xl font-mono font-bold" id="sPnl">$0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-[#909096] text-[10px] font-bold tracking-widest mb-1">ISLEM</div>
<div class="text-2xl font-mono font-bold text-white" id="sMode">ONAYLI</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-[#909096] text-[10px] font-bold tracking-widest mb-1">TARAMA</div>
<div class="text-2xl font-mono font-bold text-white" id="sScans">0</div>
</div>
</div>

<div class="grid grid-cols-12 gap-4" style="height:calc(100vh - 200px)">
<div class="col-span-12 lg:col-span-8 flex flex-col">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Canli Durum</h2>
</div>
<div class="glass rounded-lg overflow-hidden flex-1 p-6" id="statusPanel">
<div class="text-center text-[#909096]">Baslatmak icin START'a tiklayin</div>
</div>
</div>
<div class="col-span-12 lg:col-span-4 flex flex-col">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Islem Gecmisi</h2>
<span class="text-[#909096] text-xs" id="tradeCount">0</span>
</div>
<div class="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar pr-1" id="tradeList">
<div class="glass rounded-lg p-4 text-center text-[#909096] text-sm">Islem yok</div>
</div>
</div>
</div>
</div>
<script>
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('tr-TR')},1000);

function startBot(){fetch('/api/start',{method:'POST'}).then(r=>r.json()).then(d=>{setTimeout(updateStatus,2000)})}
function stopBot(){fetch('/api/stop',{method:'POST'}).then(r=>r.json()).then(d=>{setTimeout(updateStatus,1000)})}
function scanNow(){fetch('/api/scan',{method:'POST'}).then(r=>r.json()).then(d=>{setTimeout(updateStatus,3000)})}

function updateStatus(){
fetch('/api/status').then(r=>r.json()).then(d=>{
var badge=document.getElementById('statusBadge');
if(d.running&&!d.paused){badge.innerHTML='<span class="w-2 h-2 rounded-full bg-green pulse-dot"></span><span>SCANNING</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-green/10 border border-green/20 rounded text-xs font-bold text-green'}
else if(d.paused){badge.innerHTML='<span class="w-2 h-2 rounded-full bg-yellow-500 pulse-dot"></span><span>PAUSED</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs font-bold text-yellow-500'}
else{badge.innerHTML='<span class="w-2 h-2 rounded-full bg-red"></span><span>STOPPED</span>';badge.className='flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red'}

document.getElementById('sPortfolio').textContent='$'+(d.portfolio_value||0).toLocaleString(undefined,{minimumFractionDigits:2});
document.getElementById('sCash').textContent='$'+(d.cash||0).toLocaleString(undefined,{minimumFractionDigits:2});
document.getElementById('sScans').textContent=d.total_scans||0;
document.getElementById('sMode').textContent=d.auto_trade?'OTO':'ONAYLI';

var pl=d.kar_zarar||0;
var plEl=document.getElementById('sPnl');
plEl.textContent='$'+(pl>=0?'+':'')+pl.toFixed(2);
plEl.className='text-2xl font-mono font-bold '+(pl>=0?'text-green-400':'text-red-400');

var panel=document.getElementById('statusPanel');
panel.innerHTML='<div class="text-sm font-mono"><div class="mb-2"><span class="text-[#909096]">Son Karar:</span> <b>'+(d.son_karar||'-')+'</b></div><div class="mb-2"><span class="text-[#909096]">Pozisyon:</span> <b>'+(d.pozisyon_durumu||'-')+'</b></div><div class="mb-2"><span class="text-[#909096]">Son Tarama:</span> '+(d.last_scan||'-')+'</div><div class="mb-2"><span class="text-[#909096]">Toplam Islem:</span> '+(d.toplam_islem||0)+'</div><div class="mb-2"><span class="text-[#909096]">K/Z:</span> K:'+(d.kazanma||0)+' Z:'+(d.kaybetme||0)+'</div></div>';

var trades=document.getElementById('tradeList');
fetch('/api/memory').then(r=>r.json()).then(m=>{
var state=m.state||{};
document.getElementById('tradeCount').textContent=state.toplam_islem||0;
var html='';
var items=m.trades||[];
if(items.length>0){
items.slice(-10).reverse().forEach(function(t){
var color=t.pnl>0?'text-green-400':'text-red-400';
html+='<div class="glass rounded-lg p-2 text-xs font-mono"><span class="'+(t.action==='BUY'?'text-green-400':'text-red-400')+'">'+t.action+'</span> $'+t.price.toFixed(2)+' <span class="'+color+'">'+(t.pnl>0?'+':'')+t.pnl.toFixed(2)+'</span></div>';
});
trades.innerHTML=html;
} else {
trades.innerHTML='<div class="glass rounded-lg p-4 text-center text-[#909096] text-sm">Islem yok</div>';
}
}).catch(()=>{});
}).catch(()=>{});
}

updateStatus();
setInterval(updateStatus,5000);
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/status')
def api_status():
    return jsonify(bot.get_status())


@app.route('/api/memory')
def api_memory():
    stats = db.get_stats()
    trades = db.get_trade_history(20)
    scans = db.get_recent_scans(10)
    state = quant_agent.get_state()
    return jsonify({"stats": stats, "trades": trades, "scans": scans, "state": state})


@app.route('/api/start', methods=['POST'])
def api_start():
    if bot.running:
        return jsonify({"success": False, "message": "Zaten calisiyor"})
    bot.start()
    return jsonify({"success": True, "message": "Baslatildi"})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    bot.stop()
    return jsonify({"success": True})


@app.route('/api/scan', methods=['POST'])
def api_scan():
    threading.Thread(target=bot.scan, daemon=True).start()
    return jsonify({"success": True, "message": "Tarama baslatildi"})


@app.route('/api/buy', methods=['POST'])
def api_buy():
    bot.alisi_onayla()
    return jsonify({"success": True})


@app.route('/api/sell', methods=['POST'])
def api_sell():
    bot.satisi_onayla()
    return jsonify({"success": True})


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print(f"[PANEL] http://0.0.0.0:{port}")
    setup_telegram()
    app.run(host='0.0.0.0', port=port, debug=False)
