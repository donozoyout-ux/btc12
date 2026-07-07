import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify, request
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
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<script>
tailwind.config = {
darkMode: 'class',
theme: {
extend: {
fontFamily: {
sans: ['Inter', 'sans-serif'],
mono: ['JetBrains Mono', 'monospace'],
},
colors: {
surface: {
DEFAULT: '#131314',
dim: '#131314',
bright: '#3a393a',
lowest: '#0e0e0f',
low: '#1c1b1c',
},
trading: {
buy: '#22c55e',
sell: '#ef4444',
accent: '#3b82f6'
}
}
}
}
}
</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0a0e17;color:#e5e7eb;overflow:hidden;height:100vh;-webkit-font-smoothing:antialiased}
.glass{background:rgba(28,33,39,0.8);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.05)}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:#0e0e0f}
::-webkit-scrollbar-thumb{background:#3a393a;border-radius:4px}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:0.4}}
.pulse-dot{animation:pulse-dot 1.5s infinite}
.status-pulse{animation:pulse 2s cubic-bezier(0.4,0,0.6,1) infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.btn{transition:all .15s}.btn:hover{transform:scale(1.03)}.btn:active{transform:scale(0.97)}
.trade-item{transition:all .2s}.trade-item:hover{transform:translateX(4px);border-color:rgba(255,255,255,0.1)}
</style>
</head>
<body class="font-sans antialiased min-h-screen">
<header class="bg-surface-lowest border-b border-white/5 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
<div class="flex items-center space-x-4">
<h1 class="text-xl font-bold tracking-tighter text-white">BTC AI BOT</h1>
<div id="statusBadge" class="flex items-center gap-2 px-3 py-1 bg-green/10 border border-green/20 rounded text-xs font-bold text-green">
<span class="w-2 h-2 rounded-full bg-green status-pulse"></span><span>SCANNING</span>
</div>
</div>
<div class="flex items-center space-x-4" data-purpose="manuel-islem-paneli">
<div class="flex items-center bg-surface-low rounded border border-white/10 px-3 py-1.5">
<span class="text-[10px] text-gray-500 mr-2 font-bold">MİKTAR (USDT)</span>
<input id="tradeAmount" class="bg-transparent border-none text-sm font-mono text-white w-24 p-0 focus:ring-0 placeholder-gray-600" placeholder="0.00" type="number" min="0" step="0.01"/>
</div>
<button onclick="manualBuy()" class="bg-trading-buy hover:bg-green-600 text-white text-xs font-bold px-4 py-2 rounded transition-all active:scale-95">
MANUEL AL
</button>
<button onclick="manualSell()" class="bg-trading-sell hover:bg-red-600 text-white text-xs font-bold px-4 py-2 rounded transition-all active:scale-95">
MANUEL SAT
</button>
</div>
<div class="flex items-center space-x-6">
<div class="flex items-center space-x-3 text-[11px] font-bold tracking-widest text-gray-400">
<button onclick="startBot()" class="hover:text-white uppercase transition-colors">START</button>
<button onclick="stopBot()" class="hover:text-white uppercase transition-colors">STOP</button>
</div>
<button onclick="scanNow()" class="bg-trading-accent hover:bg-blue-600 text-white text-xs font-bold px-5 py-2 rounded transition-all">
SCAN
</button>
<div class="font-mono text-sm text-gray-300" id="clock">--:--:--</div>
</div>
</header>
<main class="p-4 space-y-4 max-w-[1600px] mx-auto">
<section class="grid grid-cols-1 md:grid-cols-6 gap-4" data-purpose="top-stats-cards">
<div class="bg-surface-low p-4 rounded border border-white/5 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">PORTFOY</p>
<h2 class="text-2xl font-bold font-mono text-white" id="sPortfolio">$0</h2>
</div>
<div class="bg-surface-low p-4 rounded border border-white/5 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">NAKİT</p>
<h2 class="text-2xl font-bold font-mono text-white" id="sCash">$0</h2>
</div>
<div class="bg-surface-low p-4 rounded border border-white/5 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">K/Z</p>
<h2 class="text-2xl font-bold font-mono" id="sPnl">$+0.00</h2>
</div>
<div class="bg-surface-low p-4 rounded border border-white/5 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">MOD</p>
<h2 class="text-lg font-bold font-mono" id="sMode">SIM</h2>
</div>
<div class="bg-surface-low p-4 rounded border border-white/5 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">İŞLEM</p>
<h2 class="text-2xl font-bold font-mono text-green-400">OTO</h2>
</div>
<div class="bg-surface-low p-4 rounded border border-white/5 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">TARAMA</p>
<h2 class="text-2xl font-bold font-mono text-white" id="sScans">0</h2>
</div>
<div class="bg-surface-low p-4 rounded border border-blue-500/20 text-center">
<p class="text-[10px] text-gray-500 font-bold uppercase mb-2 tracking-widest">AI MODEL</p>
<h2 class="text-lg font-bold font-mono text-blue-400" id="sAiAccuracy">---</h2>
</div>
</section>
<div class="grid grid-cols-1 lg:grid-cols-3 gap-4" style="height:calc(100vh - 220px);overflow:hidden">
<section class="lg:col-span-2 bg-surface-low rounded border border-white/5 flex flex-col" style="min-height:0">
<div class="p-4 border-b border-white/5 flex justify-between items-center">
<h3 class="text-sm font-bold text-white">Analiz Sonuçları</h3>
<span class="text-[10px] font-mono text-gray-500">REALTIME FEED: <span id="feedStatus" class="text-green-400">ACTIVE</span></span>
</div>
<div class="overflow-auto flex-grow scrollbar">
<table class="w-full text-left text-[11px] font-mono">
<thead class="sticky top-0 bg-surface-low text-gray-500 border-b border-white/5">
<tr>
<th class="px-4 py-3 font-medium uppercase tracking-wider">Zaman</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-right">Fiyat</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-right">RSI</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-right">EMA</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-right">MACD</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-center">Karar</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-right">%</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-center">Strateji</th>
<th class="px-4 py-3 font-medium uppercase tracking-wider text-center">Kaynak</th>
</tr>
</thead>
<tbody id="scanBody" class="divide-y divide-white/5 text-gray-300">
<tr><td colspan="9" class="px-4 py-8 text-center text-gray-500 italic">Veri bekleniyor...</td></tr>
</tbody>
</table>
</div>
</section>
<div class="flex flex-col gap-3 overflow-y-auto scrollbar" style="min-height:0">
<section class="bg-surface-low rounded border border-white/5 flex flex-col" style="max-height:160px;min-height:0">
<div class="p-3 border-b border-white/5 flex items-center gap-3">
<h3 class="text-sm font-bold text-white">Günlük K/Z</h3>
<span class="text-[10px] font-mono text-gray-500" id="dailyPnlTotal">HESAPLANIYOR...</span>
</div>
<div class="p-3 overflow-x-auto flex-grow scrollbar" id="dailyPnlChart">
<div class="text-gray-500 italic text-center py-4 text-sm">Veri bekleniyor...</div>
</div>
</section>
<section class="bg-surface-low rounded border border-white/5 flex flex-col" style="max-height:150px;min-height:0">
<div class="p-3 border-b border-white/5 flex justify-between items-center">
<h3 class="text-sm font-bold text-white">Karar Kayıtları</h3>
<span class="text-[10px] font-mono text-gray-500">Son 20</span>
</div>
<div class="p-2 overflow-y-auto flex-grow scrollbar text-[10px] font-mono" id="decisionList">
<div class="text-gray-500 italic text-center py-4">Kayıt bekleniyor...</div>
</div>
</section>
<section class="bg-surface-low rounded border border-white/5 flex flex-col" style="min-height:0;flex:1">
<div class="p-3 border-b border-white/5 flex justify-between items-center">
<h3 class="text-sm font-bold text-white">İşlem Geçmişi</h3>
<span class="text-[10px] font-mono text-gray-500">TOTAL: <span id="tradeCount">0</span></span>
</div>
<div class="p-2 overflow-y-auto flex-grow scrollbar" id="tradeList" data-purpose="islem-listesi">
<div class="bg-surface-lowest p-4 rounded border border-white/5 text-center text-gray-500 text-sm">İşlem yok</div>
</div>
</section>
</div>
</div>
</main>
<script>
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('tr-TR')},1000);

function startBot(){
fetch('/api/start',{method:'POST'}).then(r=>r.json()).then(d=>{
setTimeout(updateStatus,2000);
});
}

function stopBot(){
fetch('/api/stop',{method:'POST'}).then(r=>r.json()).then(d=>{
setTimeout(updateStatus,1000);
});
}

function scanNow(){
fetch('/api/scan',{method:'POST'}).then(r=>r.json()).then(d=>{
setTimeout(updateStatus,3000);
});
}

function manualBuy(){
var amount=parseFloat(document.getElementById('tradeAmount').value)||0;
if(amount<=0){alert('Lütfen geçerli bir miktar girin.');return;}
fetch('/api/manual_buy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount:amount})})
.then(r=>r.json()).then(d=>{
if(d.success){
document.getElementById('tradeAmount').value='';
showNotification('MANUEL AL emri verildi: '+amount+' USDT','success');
setTimeout(updateStatus,1000);
}else{
alert('Hata: '+(d.message||'İşlem başarısız'));
}
}).catch(e=>alert('Bağlantı hatası'));
}

function manualSell(){
var amount=parseFloat(document.getElementById('tradeAmount').value)||0;
if(amount<=0){alert('Lütfen geçerli bir miktar girin.');return;}
fetch('/api/manual_sell',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount:amount})})
.then(r=>r.json()).then(d=>{
if(d.success){
document.getElementById('tradeAmount').value='';
showNotification('MANUEL SAT emri verildi: '+amount+' USDT','success');
setTimeout(updateStatus,1000);
}else{
alert('Hata: '+(d.message||'İşlem başarısız'));
}
}).catch(e=>alert('Bağlantı hatası'));
}

function showNotification(msg,type){
var n=document.createElement('div');
n.className='fixed top-20 right-6 px-4 py-3 rounded-lg text-sm font-bold text-white z-50 transition-all transform translate-x-0 '+(type==='success'?'bg-green-600':'bg-red-600');
n.textContent=msg;
document.body.appendChild(n);
setTimeout(()=>{n.style.opacity='0';n.style.transform='translateX(100px)';setTimeout(()=>n.remove(),300);},3000);
}

function updateStatus(){
fetch('/api/status').then(r=>r.json()).then(d=>{
var badge=document.getElementById('statusBadge');
if(d.running&&!d.paused){
badge.innerHTML='<span class="w-2 h-2 rounded-full bg-green status-pulse"></span><span>SCANNING</span>';
badge.className='flex items-center gap-2 px-3 py-1 bg-green/10 border border-green/20 rounded text-xs font-bold text-green';
}else if(d.paused){
badge.innerHTML='<span class="w-2 h-2 rounded-full bg-yellow-500 status-pulse"></span><span>PAUSED</span>';
badge.className='flex items-center gap-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs font-bold text-yellow-500';
}else{
badge.innerHTML='<span class="w-2 h-2 rounded-full bg-red"></span><span>STOPPED</span>';
badge.className='flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red';
}

document.getElementById('sPortfolio').textContent='$'+(d.portfolio_value||0).toLocaleString(undefined,{minimumFractionDigits:2});
document.getElementById('sCash').textContent='$'+(d.cash||0).toLocaleString(undefined,{minimumFractionDigits:2});
document.getElementById('sScans').textContent=d.total_scans||0;

var pl=d.kar_zarar||0;
var plEl=document.getElementById('sPnl');
plEl.textContent='$'+(pl>=0?'+':'')+pl.toFixed(2);
plEl.className='text-2xl font-mono font-bold '+(pl>=0?'text-green-400':'text-red-400');

var modeEl=document.getElementById('sMode');
var m=d.executor_mode||'sim';
modeEl.textContent=m==='alpaca'?'GERÇEK':'SIM';
modeEl.className='text-lg font-mono font-bold '+(m==='alpaca'?'text-green-400':'text-yellow-400');

var aiEl=document.getElementById('sAiAccuracy');
if(d.ai_trained){
aiEl.innerHTML='%'+(d.ai_accuracy*100).toFixed(0)+' <span class="text-[10px] text-gray-500">'+d.ai_prediction_count+'t</span>';
if(d.ai_memory_size){aiEl.innerHTML+=' <span class="text-[8px] text-gray-600">| '+d.ai_memory_size+'m</span>';}
}else{
aiEl.textContent='EGITIM BEKLENIYOR';
}

}).catch(()=>{});

fetch('/api/memory').then(r=>r.json()).then(m=>{
var stats=m.stats||{};
var scans=m.scans||[];
var items=m.trades||[];

document.getElementById('tradeCount').textContent=stats.toplam_islem||0;

var scanBody=document.getElementById('scanBody');
if(scans.length>0){
var sh='';
scans.forEach(function(s){
var actionColor=s.action==='BUY'?'text-green-400':s.action==='SELL'?'text-red-400':'text-gray-500';
var actionBg=s.action==='BUY'?'bg-green-500/10 text-green-400 border border-green-500/20':s.action==='SELL'?'bg-red-500/10 text-red-400 border border-red-500/20':'bg-gray-500/10 text-gray-400 border border-white/10';
var pctColor=s.confidence>=0.6?'text-green-400':s.confidence<=0.4?'text-red-400':'text-gray-400';
sh+='<tr class="hover:bg-white/5 transition-colors">';
sh+='<td class="px-4 py-3">'+(s.time?s.time.substring(11,19):'--')+'</td>';
sh+='<td class="px-4 py-3 text-right">'+Number(s.price).toLocaleString(undefined,{minimumFractionDigits:2})+'</td>';
sh+='<td class="px-4 py-3 text-right">'+(s.rsi||0).toFixed(1)+'</td>';
sh+='<td class="px-4 py-3 text-center">'+(s.ema_cross==='bullish'?'🟢':'🔴')+'</td>';
sh+='<td class="px-4 py-3 text-right">'+(s.macd_hist||0).toFixed(1)+'</td>';
sh+='<td class="px-4 py-3 text-center"><span class="px-2 py-0.5 rounded text-[9px] font-bold '+actionBg+'">'+s.action+'</span></td>';
sh+='<td class="px-4 py-3 text-right '+pctColor+'">'+(s.confidence*100).toFixed(0)+'%</td>';
var slog=s.system_log||'';
var stratLabel='---';
var stratColor='text-gray-500';
if(slog.indexOf('STRICT')>=0){stratLabel='STRICT';stratColor='text-blue-400';}
else if(slog.indexOf('AI')>=0||s.action!=='HOLD'){stratLabel='AI';stratColor='text-purple-400';}
sh+='<td class="px-4 py-3 text-center '+stratColor+' text-[9px] font-bold">'+stratLabel+'</td>';
var srcLabel='---';
var srcColor='text-gray-600';
if(slog.indexOf('STRICT+AI')>=0){srcLabel='STRICT+AI';srcColor='text-blue-400';}
else if(slog.indexOf('STRICT')>=0){srcLabel='STRICT';srcColor='text-cyan-400';}
else if(slog.indexOf('AI')>=0||s.action!=='HOLD'){srcLabel='AI';srcColor='text-purple-400';}
sh+='<td class="px-4 py-3 text-center '+srcColor+' text-[9px] font-bold">'+srcLabel+'</td></tr>';
});
scanBody.innerHTML=sh;
}else{
scanBody.innerHTML='<tr><td colspan="9" class="px-4 py-8 text-center text-gray-500 italic">Veri bekleniyor...</td></tr>';
}

var tradeList=document.getElementById('tradeList');
if(items.length>0){
var html='';
items.forEach(function(t){
var actionColor=t.action==='BUY'?'text-green-400':'text-red-400';
var time=t.time||'';
if(time.length>10)time=time.substring(11,19);
var modeBadge=t.mode==='REAL'?'<span class="text-[8px] px-1 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 font-bold">REAL</span>':'<span class="text-[8px] px-1 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 font-bold">SIM</span>';
var pnlStr=t.pnl!==0?(t.pnl>=0?'+'+t.pnl.toFixed(2):t.pnl.toFixed(2)):'---';
var pnlColor=t.pnl>0?'text-green-400':t.pnl<0?'text-red-400':'text-gray-500';
var reasonStr=t.reason?t.reason.substring(0,15):'';
html+='<div class="bg-surface-lowest p-2.5 rounded border border-white/5 flex items-center justify-between text-[10px] font-mono trade-item">';
html+='<div class="flex items-center space-x-2 flex-shrink-0">';
html+='<span class="text-gray-500 w-[52px]">'+time+'</span>';
html+='<span class="font-bold '+actionColor+' w-[32px]">'+t.action+'</span>';
html+=modeBadge;
html+='</div>';
html+='<div class="flex items-center space-x-2 min-w-0 ml-2 flex-1 justify-end">';
html+='<span class="text-white">$'+Number(t.price).toLocaleString(undefined,{minimumFractionDigits:0})+'</span>';
if(reasonStr){html+='<span class="text-gray-500 truncate max-w-[70px]">'+reasonStr+'</span>';}
html+='<span class="px-1.5 py-0.5 rounded text-[9px] font-bold '+pnlColor+'">'+pnlStr+'</span>';
html+='</div></div>';
});
tradeList.innerHTML=html;
}else{
tradeList.innerHTML='<div class="bg-surface-lowest p-4 rounded border border-white/5 text-center text-gray-500 text-sm">İşlem yok</div>';
}
}).catch(()=>{});
}

function updateDecisions(){
fetch('/api/decisions').then(r=>r.json()).then(d=>{
var dl=document.getElementById('decisionList');
if(!dl)return;
if(d.length===0){dl.innerHTML='<div class="text-gray-500 italic text-center py-4">Kayıt yok</div>';return;}
var h='';
d.forEach(function(c){
var actColor=c.final_action==='BUY'?'text-green-400':c.final_action==='SELL'?'text-red-400':'text-gray-500';
var vetoBadge=c.ai_veto?'<span class="text-red-400 text-[8px] ml-1">VETO</span>':'';
var execBadge=c.executed?'<span class="text-green-400 text-[8px] ml-1">✓</span>':'';
h+='<div class="flex justify-between items-center py-1.5 border-b border-white/5">';
h+='<span class="text-gray-500">'+(c.time?c.time.substring(11,19):'--')+'</span>';
h+='<span class="'+actColor+' font-bold">'+c.final_action+'</span>';
h+='<span class="text-gray-400">'+c.strategy_score+'/5</span>';
h+='<span class="text-gray-600">'+c.strategy_action+'</span>';
h+='<span>'+(c.ai_prob*100).toFixed(0)+'%'+vetoBadge+execBadge+'</span>';
h+='</div>';
});
dl.innerHTML=h;
}).catch(()=>{});
}

function updateDailyPnl(){
fetch('/api/daily_pnl').then(r=>r.json()).then(d=>{
var dt=document.getElementById('dailyPnlTotal');
if(!dt)return;
if(!d||d.length===0){dt.textContent='Veri yok';return;}
var total=0,totalWin=0,totalLoss=0;
d.forEach(function(g){total+=g.pnl;if(g.pnl>0)totalWin+=g.pnl;else totalLoss+=g.pnl;});
dt.textContent='NET: '+(total>=0?'+':'')+total.toFixed(2)+'$ | +'+totalWin.toFixed(0)+'$ / '+totalLoss.toFixed(0)+'$';
var max=Math.max(...d.map(g=>Math.abs(g.pnl)),0.01);
var ch=document.getElementById('dailyPnlChart');
var h='<div style="display:flex;align-items:end;gap:6px;height:160px;padding:0 4px">';
d.forEach(function(g){
var pct=Math.abs(g.pnl)/max*100;
var color=g.pnl>=0?'#22c55e':'#ef4444';
var barH=Math.max(pct*1.2,4);
h+='<div style="flex:1;display:flex;flex-direction:column;align-items:center;height:100%;justify-content:end">';
h+='<span style="font-size:9px;color:'+color+';font-weight:700;margin-bottom:2px">'+(g.pnl>=0?'+':'')+g.pnl.toFixed(1)+'</span>';
h+='<div style="width:100%;height:'+barH+'px;background:'+color+';border-radius:3px 3px 0 0;min-height:4px;opacity:0.85"></div>';
h+='<span style="font-size:7px;color:#6b7280;margin-top:3px;white-space:nowrap">'+g.date.slice(5)+'</span>';
h+='</div>';
});
h+='</div>';
ch.innerHTML=h;
}).catch(()=>{});
}

updateStatus();
updateDecisions();
updateDailyPnl();
setInterval(updateStatus,5000);
setInterval(updateDecisions,5000);
setInterval(updateDailyPnl,10000);
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
    trades = db.get_trade_history(50)
    scans = db.get_recent_scans(20)
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


@app.route('/api/manual_buy', methods=['POST'])
def api_manual_buy():
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        if amount <= 0:
            return jsonify({"success": False, "message": "Geçersiz miktar"})
        success = trader.manual_buy(amount)
        if success:
            return jsonify({"success": True, "message": f"{amount} USDT ile alım yapıldı"})
        else:
            return jsonify({"success": False, "message": "Alım başarısız - bakiye yetersiz veya bağlantı hatası"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/manual_sell', methods=['POST'])
def api_manual_sell():
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        if amount <= 0:
            return jsonify({"success": False, "message": "Geçersiz miktar"})
        success = trader.manual_sell(amount)
        if success:
            return jsonify({"success": True, "message": f"{amount} USDT ile satım yapıldı"})
        else:
            return jsonify({"success": False, "message": "Satım başarısız - pozisyon yetersiz veya bağlantı hatası"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/debug')
def api_debug():
    import os
    db_exists = os.path.exists("trades.db")
    db_size = os.path.getsize("trades.db") if db_exists else 0
    env_keys = {k: v[:10] + "..." if v and k.endswith(("KEY", "TOKEN", "SECRET")) else v for k, v in os.environ.items() if k.startswith(("ALPACA", "TELEGRAM"))}
    return jsonify({
        "db_exists": db_exists,
        "db_size": db_size,
        "bot_running": bot.running,
        "bot_paused": bot.paused,
        "total_scans": bot.total_scans,
        "last_scan": bot.last_scan,
        "env": env_keys,
        "executor_mode": settings.executor_mode,
    })

@app.route('/api/decisions')
def api_decisions():
    from src.database import db
    return jsonify(db.get_decisions(20))

@app.route('/api/daily_pnl')
def api_daily_pnl():
    from src.database import db
    return jsonify(db.get_daily_pnl(14))

@app.route('/api/keepalive')
def api_keepalive():
    return ("", 200)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print(f"[PANEL] http://0.0.0.0:{port}")

    from src.telegram import tg
    setup_telegram()
    print("[SISTEM] Bot otomatik baslatiliyor...")
    bot.start(mesaj_gonder=False)
    print(f"[SISTEM] Bot calisiyor | Tarama araligi: {settings.check_interval}s")

    app.run(host='0.0.0.0', port=port, debug=False)
