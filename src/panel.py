import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify, request
import threading
from datetime import datetime
from src.bot import bot, setup_telegram
from src.trader import trader
from src.config import settings
from src.telegram import tg

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crypto-bot-2024'

HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRYPTO AI BOT</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<script>
tailwind.config={darkMode:"class",theme:{extend:{colors:{bg:"#0a0e17",surface:"#131314",surface2:"#1c2127",surface3:"#201f20",surface4:"#2a2a2b",surface5:"#353435",border:"#45464b",text:"#e5e2e2",text3:"#909096",green:"#10b981",red:"#f43f5e",accent:"#3b82f6"},fontFamily:{body:["Inter"],mono:["JetBrains Mono"]}}}}
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
.btn{transition:all .15s}.btn:hover{transform:scale(1.03)}.btn:active{transform:scale(0.97)}
.sell-cb{width:16px;height:16px;accent-color:#f43f5e;cursor:pointer}
</style>
</head>
<body class="flex flex-col h-screen">
<header class="bg-surface border-b border-border/30 flex items-center justify-between px-6 h-14 shrink-0">
<div class="flex items-center gap-4">
<h1 class="text-lg font-bold tracking-tight text-white">CRYPTO AI BOT</h1>
<div id="statusBadge" class="flex items-center gap-2 px-3 py-1 bg-red/10 border border-red/20 rounded text-xs font-bold text-red">
<span class="w-2 h-2 rounded-full bg-red"></span>
<span>STOPPED</span>
</div>
<div id="aiBadge" class="flex items-center gap-1 px-2 py-0.5 bg-accent/10 border border-accent/20 rounded text-[10px] font-bold text-accent">
<span class="material-symbols-outlined text-xs">psychology</span>
<span>AI ACTIVE</span>
</div>
</div>
<div class="flex items-center gap-3">
<button onclick="startBot()" class="btn px-4 py-1.5 bg-green hover:bg-green/80 text-black text-xs font-bold rounded flex items-center gap-1">
<span class="material-symbols-outlined text-sm">play_arrow</span> START
</button>
<button onclick="stopBot()" class="btn px-4 py-1.5 bg-red hover:bg-red/80 text-white text-xs font-bold rounded flex items-center gap-1">
<span class="material-symbols-outlined text-sm">stop</span> STOP
</button>
<button onclick="pauseBot()" class="btn px-4 py-1.5 bg-surface4 hover:bg-surface5 text-text text-xs font-bold rounded flex items-center gap-1">
<span class="material-symbols-outlined text-sm">pause</span> PAUSE
</button>
<button onclick="scanNow()" class="btn px-4 py-1.5 bg-accent hover:bg-accent/80 text-white text-xs font-bold rounded flex items-center gap-1">
<span class="material-symbols-outlined text-sm">radar</span> SCAN
</button>
<div class="w-px h-6 bg-border/30 mx-1"></div>
<span class="text-text3 text-xs font-mono" id="clock"></span>
</div>
</header>
<div class="flex flex-1 overflow-hidden">
<main class="flex-1 overflow-y-auto p-6 scrollbar">
<div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
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
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">AI BASARI</div>
<div class="text-2xl font-mono font-bold text-accent" id="sWinRate">%0</div>
</div>
</div>

<div class="grid grid-cols-12 gap-4" style="height:calc(100vh - 200px)">
<div class="col-span-12 lg:col-span-8 flex flex-col">
<div class="flex items-center gap-6 mb-3 border-b border-border/20 pb-2">
<button onclick="switchTab('scan')" id="tabScan" class="text-xs font-bold text-white border-b-2 border-accent pb-1 cursor-pointer">TARAMA</button>
<button onclick="switchTab('positions')" id="tabPos" class="text-xs font-bold text-text3 border-b-2 border-transparent pb-1 cursor-pointer">POZISYONLAR</button>
<button onclick="switchTab('ai')" id="tabAi" class="text-xs font-bold text-text3 border-b-2 border-transparent pb-1 cursor-pointer">AI HAFIZA</button>
</div>

<div id="scanPanel" class="flex flex-col flex-1">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Tarama Sonuclari</h2>
<div class="flex gap-2">
<button onclick="filterAction('all')" class="px-2 py-0.5 text-[10px] font-bold border border-border/30 rounded text-text3 hover:text-white">ALL</button>
<button onclick="filterAction('BUY')" class="px-2 py-0.5 text-[10px] font-bold border border-green/30 rounded text-green hover:bg-green/10">BUY</button>
<button onclick="filterAction('SELL')" class="px-2 py-0.5 text-[10px] font-bold border border-red/30 rounded text-red hover:bg-red/10">SELL</button>
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
<tbody id="scanBody" class="divide-y divide-border/10">
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
<button onclick="sellSelected()" class="btn px-3 py-1 bg-red hover:bg-red/80 text-white text-[10px] font-bold rounded">SECILENLERI SAT</button>
<button onclick="sellAll()" class="btn px-3 py-1 bg-red hover:bg-red/80 text-white text-[10px] font-bold rounded">HEPSINI SAT</button>
</div>
</div>
<div class="glass rounded-lg overflow-hidden flex-1">
<table class="w-full text-left">
<thead class="bg-surface3/50 border-b border-border/20">
<tr>
<th class="px-4 py-3 w-10"><input type="checkbox" class="sell-cb" onchange="toggleAll(this)"></th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">COIN</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">MIKTAR</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">GIRIS</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">DEGER</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">K/Z</th>
<th class="px-4 py-3 w-16"></th>
</tr>
</thead>
<tbody id="posBody" class="divide-y divide-border/10">
<tr><td colspan="7" class="px-4 py-12 text-center text-text3 italic">Pozisyon yok</td></tr>
</tbody>
</table>
</div>
</div>

<div id="aiPanel" class="flex flex-col flex-1 hidden">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white flex items-center gap-2">
<span class="material-symbols-outlined text-accent">psychology</span> AI HAFIZA
</h2>
<button onclick="refresh()" class="btn px-3 py-1 bg-accent hover:bg-accent/80 text-white text-[10px] font-bold rounded">YENILE</button>
</div>
<div class="grid grid-cols-3 gap-3 mb-4">
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">BASARI ORANI</div>
<div class="text-3xl font-mono font-bold text-accent" id="aiWinRate">%0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">TOPLAM ISLEM</div>
<div class="text-3xl font-mono font-bold text-white" id="aiTotal">0</div>
</div>
<div class="glass rounded-lg p-4 text-center">
<div class="text-text3 text-[10px] font-bold tracking-widest mb-1">TOPLAM K/Z</div>
<div class="text-3xl font-mono font-bold" id="aiPnl">$0</div>
</div>
</div>
<div class="glass rounded-lg overflow-hidden flex-1">
<table class="w-full text-left">
<thead class="bg-surface3/50 border-b border-border/20">
<tr>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">COIN</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3">ISLEM</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">FIYAT</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">GUVEN</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">SONUC</th>
<th class="px-4 py-3 text-[10px] font-bold tracking-widest text-text3 text-right">K/Z</th>
</tr>
</thead>
<tbody id="aiBody" class="divide-y divide-border/10">
<tr><td colspan="6" class="px-4 py-12 text-center text-text3 italic">Islem gecmisi yok</td></tr>
</tbody>
</table>
</div>
</div>
</div>

<div class="col-span-12 lg:col-span-4 flex flex-col">
<div class="flex items-center justify-between mb-3">
<h2 class="text-sm font-bold text-white">Sinyaller</h2>
<span class="text-text3 text-xs" id="signalCount">0</span>
</div>
<div class="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar pr-1" id="signalsList">
<div class="glass rounded-lg p-4 text-center text-text3 text-sm">Sinyal yok</div>
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
    ['scan','positions','ai'].forEach(x=>{
        var el=document.getElementById('tab'+x.charAt(0).toUpperCase()+x.slice(1));
        if(el){
            el.className=x===t?'text-xs font-bold text-white border-b-2 border-accent pb-1 cursor-pointer'
                          :'text-xs font-bold text-text3 border-b-2 border-transparent pb-1 cursor-pointer';
        }
        var panel=document.getElementById(x+'Panel');
        if(panel){
            panel.className=x===t?'flex flex-col flex-1':'flex flex-col flex-1 hidden';
        }
    });
}

function startBot(){fetch('/api/start',{method:'POST'}).then(r=>r.json()).then(d=>{toast(d.message,d.success?'success':'error');setTimeout(refresh,2000)})}
function stopBot(){fetch('/api/stop',{method:'POST'}).then(r=>r.json()).then(d=>{toast('Durdu','info');setTimeout(refresh,1000)})}
function pauseBot(){fetch('/api/pause',{method:'POST'}).then(r=>r.json()).then(d=>{toast(d.paused?'Duraklatildi':'Devam','info');setTimeout(refresh,1000)})}
function scanNow(){fetch('/api/scan',{method:'POST'}).then(r=>r.json()).then(d=>{toast('Tarama baslatildi','success');setTimeout(refresh,5000)})}
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

function toggleAll(el){document.querySelectorAll('.pos-cb').forEach(cb=>cb.checked=el.checked)}

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

        document.getElementById('sTotalScans').textContent=d.total_scans||0;

        if(d.balance){
            var pv=parseFloat(d.balance.portfolio_value||0);
            var cash=parseFloat(d.balance.cash||0);
            document.getElementById('sPortfolio').textContent='$'+pv.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
            document.getElementById('sCash').textContent='$'+cash.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
            var positions=d.positions||[];
            var totalPnl=0;positions.forEach(p=>totalPnl+=p.unrealized_pl||0);
            var el=document.getElementById('sPnl');
            el.textContent='$'+(totalPnl>=0?'+':'')+totalPnl.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
            el.className='text-2xl font-mono font-bold '+(totalPnl>=0?'text-green':'text-red');
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
                html+='<tr class="hover:bg-white/5 transition-colors">';
                html+='<td class="px-4 py-3 font-mono text-sm font-bold">'+r.symbol+'</td>';
                html+='<td class="px-4 py-3">'+badge+'</td>';
                html+='<td class="px-4 py-3"><div class="w-20 bg-surface4 h-1.5 rounded-full overflow-hidden"><div class="'+confColor+' h-full" style="width:'+conf*100+'%"></div></div><span class="font-mono text-[11px] mt-1 block">'+(conf*100).toFixed(0)+'%</span></td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">$'+(r.price||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right '+rsiColor+'">'+(r.rsi||0).toFixed(1)+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right text-text3">'+(r.volume_ratio||0).toFixed(1)+'x</td>';
                html+='</tr>';
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
            positions.forEach(p=>{
                var pl=p.unrealized_pl||0;
                var entry=p.avg_entry_price||0;
                var mv=p.market_value||0;
                var yuzde=entry>0?((mv-entry*p.qty)/(entry*p.qty)*100):0;
                var plColor=pl>=0?'text-green':'text-red';
                html+='<tr class="hover:bg-white/5 transition-colors">';
                html+='<td class="px-4 py-3"><input type="checkbox" class="sell-cb pos-cb" data-sym="'+p.symbol+'"></td>';
                html+='<td class="px-4 py-3 font-mono text-sm font-bold">'+p.symbol+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">'+p.qty.toFixed(6)+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">$'+entry.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">$'+mv.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right '+plColor+'">$'+pl.toFixed(2)+' ('+yuzde.toFixed(1)+'%)</td>';
                html+='<td class="px-4 py-3 text-right"><button onclick="sellCoin(\\''+p.symbol+'\\')" class="btn px-3 py-1 bg-red/20 hover:bg-red text-red hover:text-white text-[10px] font-bold rounded">SAT</button></td>';
                html+='</tr>';
            });
            posBody.innerHTML=html;
        }else{
            posBody.innerHTML='<tr><td colspan="7" class="px-4 py-12 text-center text-text3 italic">Pozisyon yok</td></tr>';
        }

        var sigs=d.last_signals||{};
        var sigKeys=Object.keys(sigs);
        document.getElementById('signalCount').textContent=sigKeys.length+' sinyal';
        var sigList=document.getElementById('signalsList');
        if(sigKeys.length>0){
            var html='';
            sigKeys.forEach(coin=>{
                var s=sigs[coin];
                var color=s.action==='BUY'?'green':'red';
                var border=s.action==='BUY'?'border-green':'border-red';
                html+='<div class="glass rounded-lg p-3 border-l-4 '+border+'"><div class="font-bold text-'+color+'">'+coin+' - '+s.action+'</div><div class="text-xs text-text3 font-mono">$'+(s.price||0).toFixed(2)+' | Guven: '+(s.confidence*100).toFixed(0)+'%</div>'+(s.reason?'<div class="text-[10px] text-text3 mt-1 italic">'+s.reason.substring(0,60)+'</div>':'')+'</div>';
            });
            sigList.innerHTML=html;
        }

        document.getElementById('scanStatus').textContent=d.running?(d.paused?'DURAKLATILDI':'Tarama aktif - BTC, ETH'):'Durdu';
    }).catch(e=>console.log('Status error:',e));

    fetch('/api/memory').then(r=>r.json()).then(d=>{
        var stats=d.stats||{};
        document.getElementById('sWinRate').textContent='%' + (stats.win_rate||0);
        var wr=document.getElementById('sWinRate');
        wr.className='text-2xl font-mono font-bold '+(stats.win_rate>=50?'text-green':stats.win_rate>=30?'text-yellow-500':'text-red');

        document.getElementById('aiWinRate').textContent='%' + (stats.win_rate||0);
        document.getElementById('aiTotal').textContent=stats.total||0;
        var pnl=stats.total_pnl||0;
        var pnlEl=document.getElementById('aiPnl');
        pnlEl.textContent='$'+(pnl>=0?'+':'')+pnl.toFixed(4);
        pnlEl.className='text-3xl font-mono font-bold '+(pnl>=0?'text-green':'text-red');

        var recent=d.recent||[];
        var aiBody=document.getElementById('aiBody');
        if(recent.length>0){
            var html='';
            recent.reverse().forEach(t=>{
                var outcome=t.outcome==='WIN'?'<span class="text-green font-bold">KAZANDI</span>'
                    :t.outcome==='LOSS'?'<span class="text-red font-bold">KAYBETTI</span>'
                    :t.outcome==='BREAKEVEN'?'<span class="text-text3">BESLEME</span>'
                    :'<span class="text-text3">---</span>';
                html+='<tr class="hover:bg-white/5 transition-colors">';
                html+='<td class="px-4 py-3 font-mono text-sm font-bold">'+t.symbol+'</td>';
                html+='<td class="px-4 py-3"><span class="px-2 py-0.5 text-[10px] font-bold rounded '+(t.action==='BUY'?'bg-green/10 text-green':'bg-red/10 text-red')+'">'+t.action+'</span></td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">$'+t.price.toFixed(2)+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right">'+(t.confidence*100).toFixed(0)+'%</td>';
                html+='<td class="px-4 py-3 text-right">'+outcome+'</td>';
                html+='<td class="px-4 py-3 font-mono text-sm text-right '+(t.pnl>=0?'text-green':'text-red')+'">$'+(t.pnl>=0?'+':'')+t.pnl.toFixed(4)+'</td>';
                html+='</tr>';
            });
            aiBody.innerHTML=html;
        }
    }).catch(e=>console.log('Memory error:',e));
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
    return jsonify(bot.get_status())


@app.route('/api/start', methods=['POST'])
def api_start():
    if bot.running:
        return jsonify({"success": False, "message": "Bot zaten calisiyor"})
    bot.start()
    return jsonify({"success": True, "message": "Bot baslatildi - BTC, ETH"})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    bot.stop()
    return jsonify({"success": True})


@app.route('/api/pause', methods=['POST'])
def api_pause():
    state = bot.toggle_pause()
    return jsonify({"success": True, "paused": state})


@app.route('/api/scan', methods=['POST'])
def api_scan():
    threading.Thread(target=bot.scan, daemon=True).start()
    return jsonify({"success": True, "message": "Tarama baslatildi"})


@app.route('/api/buy', methods=['POST'])
def api_buy():
    try:
        data = request.get_json()
        sym = data.get("symbol", "BTC/USD")
        result = trader.buy(sym)
        return jsonify({
            "success": True,
            "message": f"{sym} alindi - ${result['price']:,.2f} / {result['qty']:.6f}"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)[:200]})


@app.route('/api/sell', methods=['POST'])
def api_sell():
    try:
        data = request.get_json()
        sym = data.get("symbol", "")
        result = trader.sell(sym)
        if result:
            return jsonify({
                "success": True,
                "message": f"{sym} satildi - K/Z: ${result['pl']:+,.4f}"
            })
        return jsonify({"success": False, "message": f"{sym} pozisyon yok"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)[:200]})


@app.route('/api/sell-multi', methods=['POST'])
def api_sell_multi():
    try:
        data = request.get_json()
        symbols = data.get("symbols", [])
        sold = []
        for sym in symbols:
            result = trader.sell(sym)
            if result:
                sold.append(sym)
        return jsonify({"success": True, "message": f"{len(sold)} coin satildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)[:200]})


@app.route('/api/sell-all', methods=['POST'])
def api_sell_all():
    try:
        results = trader.sell_all()
        return jsonify({"success": True, "message": f"{len(results)} coin satildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)[:200]})


@app.route('/api/memory')
def api_memory():
    return jsonify(bot.get_memory_data())


@app.route('/api/keepalive')
def api_keepalive():
    return jsonify({"status": "ok", "running": bot.running, "scans": bot.total_scans})


if __name__ == '__main__':
    import os

    errors = settings.validate()
    if errors:
        for e in errors:
            print(f"[WARN] {e}")

    print("[SYSTEM] Bot baslatiliyor...")
    setup_telegram()
    print("[SYSTEM] Telegram dinleniyor...")

    port = int(os.environ.get('PORT', 5000))
    print(f"[PANEL] http://0.0.0.0:{port}")
    print(f"[COIN] BTC, ETH | Islem: ${settings.position_size_usd}")
    print(f"[AI] SL: %{settings.stop_loss_pct*100:.1f}  TP: %{settings.take_profit_pct*100:.1f}")

    tg.send(
        f"<b>SISTEM HAZIR</b>\n\n"
        f"Coin: BTC, ETH\n"
        f"Islem: ${settings.position_size_usd}\n\n"
        f"Basla: <code>/start</code>\n"
        f"Komutlar: <code>/help</code>"
    )

    app.run(host='0.0.0.0', port=port, debug=False)
