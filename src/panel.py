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
<title>BTC AI BOT Dashboard</title>
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
          DEFAULT: '#0b0f19',
          dim: '#131b2d',
          bright: '#242f49',
          lowest: '#060a12',
          low: '#0e1424',
        },
        trading: {
          buy: '#10b981',
          sell: '#ef4444',
          accent: '#3b82f6'
        }
      }
    }
  }
}
</script>
<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
body {
  font-family: 'Inter', sans-serif;
  background: radial-gradient(circle at top, #0f172a 0%, #020617 100%);
  color: #f1f5f9;
  min-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
  -webkit-tap-highlight-color: transparent;
}
.glass {
  background: rgba(14, 20, 36, 0.45);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
}
.glass-glow {
  box-shadow: 0 0 20px rgba(59, 130, 246, 0.15);
}
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: #060a12;
}
::-webkit-scrollbar-thumb {
  background: #1e293b;
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #334155;
}
@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 5px rgba(16, 185, 129, 0.2); }
  50% { box-shadow: 0 0 15px rgba(16, 185, 129, 0.6); }
}
.pulse-glow-green {
  animation: pulse-glow 2s infinite;
}
.btn {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.btn:hover {
  transform: translateY(-1px);
}
.btn:active {
  transform: translateY(1px);
}
.trade-item {
  transition: all 0.2s ease;
}
.trade-item:hover {
  background: rgba(255, 255, 255, 0.03);
  transform: translateX(2px);
}
/* === MOBILE RESPONSIVE === */
@media (max-width: 768px) {
  main { padding: 12px !important; }
  header { padding: 10px 12px !important; flex-direction: column !important; gap: 10px; }
  .glass { padding: 10px !important; }
  section[data-purpose="top-stats-cards"] { grid-template-columns: repeat(2, 1fr) !important; gap: 8px !important; }
  section[data-purpose="ai-consensus-panel"] .grid { grid-template-columns: repeat(2, 1fr) !important; }
  .tradingview-widget-container { height: 260px !important; }
  #tradeAmount { width: 60px !important; }
  .gemini-brain-grid { grid-template-columns: 1fr !important; }
}
@media (max-width: 480px) {
  section[data-purpose="top-stats-cards"] { grid-template-columns: 1fr 1fr !important; }
  section[data-purpose="ai-consensus-panel"] .grid { grid-template-columns: 1fr 1fr !important; }
  h2 { font-size: 16px !important; }
}
</style>
</head>
<body class="font-sans antialiased pb-12">
<header class="bg-surface-lowest/80 backdrop-blur-md border-b border-white/5 px-6 py-4 flex flex-col md:flex-row items-center justify-between sticky top-0 z-50">
  <div class="flex items-center space-x-4 mb-4 md:mb-0">
    <div class="p-2.5 bg-gradient-to-tr from-blue-600 to-indigo-600 rounded-xl shadow-lg shadow-indigo-500/20">
      <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path>
      </svg>
    </div>
    <div>
      <h1 class="text-lg font-extrabold tracking-tight text-white flex items-center gap-2">
        BTC AI TRADING <span class="text-xs px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">PRO</span>
      </h1>
      <p class="text-[10px] text-gray-500 font-mono tracking-wider">VERSION 3.0.0 • 5-AGENT AI CONSENSUS</p>
    </div>
  </div>

  <div class="flex flex-wrap items-center gap-4 justify-center">
    <div id="statusBadge" class="flex items-center gap-2 px-3.5 py-1.5 bg-trading-buy/10 border border-trading-buy/20 rounded-lg text-xs font-bold text-trading-buy pulse-glow-green">
      <span class="w-2 h-2 rounded-full bg-trading-buy"></span><span>SİNYAL BEKLENİYOR</span>
    </div>

    <!-- MOD SEÇİMİ: SİMÜLASYON / BINANCE -->
    <div class="flex items-center gap-1 bg-surface-lowest border border-white/10 rounded-lg p-1" data-purpose="mode-toggle">
      <button id="btnSim" onclick="setMode('sim')" class="btn text-[10px] font-extrabold px-3 py-1.5 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30">🟡 SİMÜLASYON</button>
      <button id="btnBinance" onclick="setMode('binance')" class="btn text-[10px] font-extrabold px-3 py-1.5 rounded-md text-gray-400 hover:text-white">🔵 BINANCE HESAP</button>
    </div>

    <!-- Manuel İşlem Modülü -->
    <div class="flex items-center bg-surface-low rounded-lg border border-white/10 px-3 py-1" data-purpose="manuel-islem-paneli">
      <span class="text-[9px] text-gray-500 mr-2 font-bold tracking-wider">MİKTAR (USDT)</span>
      <input id="tradeAmount" class="bg-transparent border-none text-sm font-mono text-white w-20 p-0 focus:ring-0 focus:outline-none placeholder-gray-600" placeholder="500.00" type="number" min="0" step="10"/>
    </div>
    <!-- Simülasyon Sermayesi -->
    <div class="flex items-center bg-surface-low rounded-lg border border-white/10 px-3 py-1" data-purpose="sim-capital-paneli">
      <span class="text-[9px] text-gray-500 mr-2 font-bold tracking-wider">SIM. SERMAYE</span>
      <input id="simCapital" class="bg-transparent border-none text-sm font-mono text-white w-20 p-0 focus:ring-0 focus:outline-none placeholder="500" type="number" min="10" step="10" value="500"/>
      <button onclick="setSimCapital()" class="btn bg-slate-600 hover:bg-slate-500 text-white text-[9px] font-bold px-2 py-0.5 rounded ml-1">AYARLA</button>
      <button onclick="resetSim()" class="btn bg-rose-600/80 hover:bg-rose-500 text-white text-[9px] font-bold px-2 py-0.5 rounded ml-1" title="Simülasyonu başlangıç sermayesine sıfırla">SIFIRLA</button>
    </div>
    <div class="flex items-center gap-2">
      <button onclick="manualBuy()" class="btn bg-trading-buy hover:bg-emerald-600 text-white text-xs font-extrabold px-3 py-2 rounded-lg shadow-lg shadow-emerald-500/20">
        AL
      </button>
      <button onclick="manualSell()" class="btn bg-trading-sell hover:bg-rose-600 text-white text-xs font-extrabold px-3 py-2 rounded-lg shadow-lg shadow-rose-500/20">
        SAT
      </button>
    </div>

    <!-- Sistem Kontrolleri -->
    <div class="flex items-center gap-2 bg-surface-lowest border border-white/5 rounded-lg p-1">
      <button onclick="startBot()" class="btn text-[10px] font-bold text-gray-400 hover:text-white px-2.5 py-1 rounded">START</button>
      <button onclick="stopBot()" class="btn text-[10px] font-bold text-gray-400 hover:text-white px-2.5 py-1 rounded">STOP</button>
      <button onclick="scanNow()" class="btn bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold px-3 py-1 rounded-md shadow-md shadow-blue-500/10">
        TARA
      </button>
    </div>

    <div class="font-mono text-sm text-slate-400 bg-surface-lowest px-3 py-1.5 border border-white/5 rounded-lg" id="clock">--:--:--</div>

    <!-- Binance Bağlantı Durumu -->
    <div id="binanceStatusBadge" class="flex items-center gap-2 px-3 py-1.5 bg-slate-500/10 border border-white/10 rounded-lg text-[10px] font-bold text-slate-400 cursor-pointer" onclick="testBinance()" title="Binance bağlantısını test et">
      <span class="w-2 h-2 rounded-full bg-slate-500"></span><span id="binanceStatusText">BINANCE: ?</span>
    </div>

    <!-- Günlük Hedef %1 Takipçisi -->
    <div id="goalBadge" class="flex items-center gap-2 px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-[10px] font-bold text-indigo-300" title="Günlük %1 hedefi">
      <span>🎯 HEDEF</span><span id="goalText">--</span>
    </div>
  </div>
</header>

<main class="p-6 space-y-6 max-w-[1700px] mx-auto">
  <!-- Ana Metrik Kartları -->
  <section class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4" data-purpose="top-stats-cards">
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">PORTFÖY DEĞERİ</span>
      <h2 class="text-xl font-extrabold font-mono text-white mt-1" id="sPortfolio">$0</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">KULLANILABİLİR NAKİT</span>
      <h2 class="text-xl font-extrabold font-mono text-white mt-1" id="sCash">$0</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">NET K/Z</span>
      <h2 class="text-xl font-extrabold font-mono mt-1" id="sPnl">$+0.00</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">HESAP MODU</span>
      <h2 class="text-base font-extrabold font-mono mt-1" id="sMode">---</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">YÜRÜTME MODU</span>
      <h2 class="text-xl font-extrabold font-mono text-emerald-400 mt-1">OTOMATİK</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">TOPLAM TARAMA</span>
      <h2 class="text-xl font-extrabold font-mono text-white mt-1" id="sScans">0</h2>
    </div>
    <div class="glass p-4 rounded-xl border border-blue-500/20 flex flex-col justify-between">
      <span class="text-[10px] text-blue-400 font-bold uppercase tracking-wider">AI MODEL DOĞRULUK</span>
      <h2 class="text-sm font-extrabold font-mono text-blue-400 mt-1" id="sAiAccuracy">---</h2>
    </div>
  </section>

  <!-- 🧠 GEMINi 5-BEYiN AI TARTIŞMA PANELi -->
  <section class="glass rounded-2xl p-5 border border-cyan-500/15" data-purpose="gemini-debate-panel" id="geminiSection">
    <div class="border-b border-white/5 pb-3 mb-4 flex items-center justify-between">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 animate-pulse"></span>
        🧠 Gemini 5-Beyin AI Tartışma Paneli
      </h3>
      <div class="flex items-center gap-3">
        <button onclick="openBrainsEditor()" class="btn text-[9px] font-bold px-2.5 py-1 rounded-md bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25">⚙️ AI BEYİNLERİNİ DÜZENLE</button>
        <span class="text-[9px] font-mono text-cyan-400 font-bold" id="geminiStatus">BAĞLANIYOR...</span>
        <span id="geminiFinalBadge" class="px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-slate-500/10 text-slate-400 border border-white/10">---</span>
      </div>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-5 gap-3 gemini-brain-grid" id="geminiBrainCards">
      <div class="text-slate-500 italic text-center py-6 text-xs col-span-5">Gemini API bağlanıyor...</div>
    </div>
    <div class="mt-3 p-3 bg-surface-lowest/60 rounded-xl border border-white/5" id="geminiSummaryBox" style="display:none">
      <span class="text-[9px] text-slate-500 font-bold uppercase tracking-wider">GENEL DEĞERLENDİRME</span>
      <p class="text-xs text-slate-300 mt-1 leading-relaxed" id="geminiSummaryText"></p>
    </div>
  </section>

  <!-- 5 AI AJAN KONSENSÜS PANELİ -->
  <section class="glass rounded-2xl p-5 glass-glow border border-purple-500/10" data-purpose="ai-consensus-panel">
    <div class="border-b border-white/5 pb-3 mb-4 flex items-center justify-between">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span> 5 AI Ajan Konsensüs Sistemi
      </h3>
      <div class="flex items-center gap-3">
        <span class="text-[10px] font-mono text-purple-400 font-bold" id="consensusRate">---</span>
        <span id="consensusBadge" class="px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-slate-500/10 text-slate-400 border border-white/10">BEKLE</span>
      </div>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-5 gap-3" id="agentCards">
      <div class="text-slate-500 italic text-center py-6 text-xs col-span-5">Ajan verileri yükleniyor...</div>
    </div>
  </section>

  <!-- Grafik ve Karar Kayıtları Grid -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Sol ve Orta Kolon (Grafik ve Sonuç Tablosu) -->
    <div class="lg:col-span-2 space-y-6 flex flex-col">
      <!-- TradingView Grafiği -->
      <section class="glass rounded-2xl overflow-hidden glass-glow">
        <div class="px-5 py-4 border-b border-white/5 flex items-center justify-between bg-surface-lowest/40">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span> Canlı Fiyat Grafiği (BTC/USD)
          </h3>
          <span class="text-[10px] font-mono text-slate-500">KAYNAK: TRADINGVIEW</span>
        </div>
        <!-- TradingView Widget BEGIN -->
        <div class="tradingview-widget-container w-full h-[380px]">
          <div id="tradingview_chart" class="w-full h-full"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
            "width": "100%",
            "height": "100%",
            "symbol": "COINBASE:BTCUSD",
            "interval": "5",
            "timezone": "Europe/Istanbul",
            "theme": "dark",
            "style": "1",
            "locale": "tr",
            "toolbar_bg": "#0e1424",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": "tradingview_chart"
          });
          </script>
        </div>
        <!-- TradingView Widget END -->
      </section>

      <!-- Analiz Sonuçları Tablosu -->
      <section class="glass rounded-2xl flex flex-col flex-grow">
        <div class="px-5 py-4 border-b border-white/5 flex justify-between items-center bg-surface-lowest/40">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Teknik Analiz Beslemesi
          </h3>
          <span class="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span> CANLI YAYIN
          </span>
        </div>
        <div class="overflow-x-auto max-h-[320px] scrollbar">
          <table class="w-full text-left text-xs font-mono">
            <thead class="sticky top-0 bg-surface-low text-slate-400 border-b border-white/10 text-[10px] uppercase tracking-wider">
              <tr>
                <th class="px-5 py-3 font-semibold">Zaman</th>
                <th class="px-5 py-3 font-semibold text-right">Fiyat</th>
                <th class="px-5 py-3 font-semibold text-right">RSI</th>
                <th class="px-5 py-3 font-semibold text-center">EMA Cross</th>
                <th class="px-5 py-3 font-semibold text-right">MACD</th>
                <th class="px-5 py-3 font-semibold text-center">Karar</th>
                <th class="px-5 py-3 font-semibold text-right">Güven</th>
                <th class="px-5 py-3 font-semibold text-center">Strateji</th>
                <th class="px-5 py-3 font-semibold text-center">Kaynak</th>
              </tr>
            </thead>
            <tbody id="scanBody" class="divide-y divide-white/5 text-slate-300">
              <tr>
                <td colspan="9" class="px-5 py-8 text-center text-slate-500 italic">Analiz verileri yükleniyor...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- Sağ Kolon (Kayıtlar, Günlük Grafik, Geçmiş) -->
    <div class="space-y-6">
      <!-- Günlük Kar / Zarar Barları -->
      <section class="glass rounded-2xl flex flex-col p-5">
        <div class="border-b border-white/5 pb-3 mb-4 flex items-center justify-between">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span> Günlük Performans
          </h3>
          <span class="text-[10px] font-mono text-indigo-400 font-bold" id="dailyPnlTotal">HESAPLANIYOR...</span>
        </div>
        <div class="overflow-x-auto py-2" id="dailyPnlChart">
          <div class="text-slate-500 italic text-center py-4 text-xs">Yükleniyor...</div>
        </div>
      </section>

      <!-- Konsensüs İstatistikleri -->
      <section class="glass rounded-2xl flex flex-col p-5 border border-purple-500/10">
        <div class="border-b border-white/5 pb-3 mb-3 flex justify-between items-center">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-purple-500"></span> Ajan Doğruluk Sıralaması
          </h3>
          <span class="text-[10px] font-mono text-purple-400">AI PERFORMANS</span>
        </div>
        <div class="space-y-2" id="agentRanking">
          <div class="text-slate-500 italic text-center py-4 text-xs">Hesaplanıyor...</div>
        </div>
      </section>

      <!-- Karar Günlükleri -->
      <section class="glass rounded-2xl flex flex-col p-5">
        <div class="border-b border-white/5 pb-3 mb-3 flex justify-between items-center">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span> Stratejik Karar Logları
          </h3>
          <span class="text-[10px] font-mono text-slate-500">Son 20 Karar</span>
        </div>
        <div class="max-h-[180px] overflow-y-auto scrollbar text-[10px] font-mono space-y-1.5" id="decisionList">
          <div class="text-slate-500 italic text-center py-4">Bekleniyor...</div>
        </div>
      </section>

      <!-- İşlem Geçmişi -->
      <section class="glass rounded-2xl flex flex-col p-5">
        <div class="border-b border-white/5 pb-3 mb-3 flex justify-between items-center">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span> Gerçekleşen Emir Geçmişi
          </h3>
          <span class="text-[10px] font-mono text-slate-500">TOPLAM: <span id="tradeCount" class="text-rose-400 font-bold">0</span></span>
        </div>
        <div class="max-h-[280px] overflow-y-auto scrollbar space-y-2" id="tradeList" data-purpose="islem-listesi">
          <div class="text-slate-500 italic text-center py-6 text-xs">Emir kaydı bulunamadı</div>
        </div>
      </section>
    </div>
  </div>
</main>

<script>
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('tr-TR');
}, 1000);

function startBot() {
  fetch('/api/start', {method: 'POST'}).then(r => r.json()).then(d => {
    showNotification('Algoritma başlatıldı!', 'success');
    setTimeout(updateStatus, 1500);
  });
}

function stopBot() {
  fetch('/api/stop', {method: 'POST'}).then(r => r.json()).then(d => {
    showNotification('Algoritma durduruldu.', 'warning');
    setTimeout(updateStatus, 1000);
  });
}

function scanNow() {
  fetch('/api/scan', {method: 'POST'}).then(r => r.json()).then(d => {
    showNotification('Piyasa analizi tetiklendi...', 'success');
    setTimeout(updateStatus, 2000);
  });
}

function manualBuy() {
  var amountInput = document.getElementById('tradeAmount');
  var amount = parseFloat(amountInput.value) || 500;
  if (amount <= 0) {
    alert('Geçersiz miktar.');
    return;
  }
  showNotification('Alım emri gönderiliyor...', 'info');
  fetch('/api/manual_buy', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({amount: amount})
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      showNotification(d.message, 'success');
      setTimeout(() => { updateStatus(); updateDailyPnl(); updateDecisions(); }, 1500);
    } else {
      showNotification('Hata: ' + d.message, 'error');
    }
  }).catch(() => showNotification('Sunucu bağlantı hatası', 'error'));
}

function manualSell() {
  showNotification('Satım emri gönderiliyor...', 'info');
  fetch('/api/manual_sell', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({amount: 1})
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      showNotification(d.message, 'success');
      setTimeout(() => { updateStatus(); updateDailyPnl(); updateDecisions(); }, 1500);
    } else {
      showNotification('Hata: ' + d.message, 'error');
    }
  }).catch(() => showNotification('Sunucu bağlantı hatası', 'error'));
}

function showNotification(msg, type) {
  var n = document.createElement('div');
  var bg = 'bg-blue-600';
  if (type === 'success') bg = 'bg-emerald-600';
  if (type === 'warning') bg = 'bg-amber-600';
  if (type === 'error') bg = 'bg-rose-600';
  
  n.className = 'fixed bottom-6 right-6 px-4 py-3 rounded-xl text-xs font-bold text-white z-50 transition-all duration-300 transform translate-y-10 opacity-0 shadow-lg shadow-black/40 border border-white/10 ' + bg;
  n.textContent = msg;
  document.body.appendChild(n);
  
  // Slide up and fade in
  setTimeout(() => {
    n.classList.remove('translate-y-10', 'opacity-0');
  }, 10);
  
  // Fade out and remove
  setTimeout(() => {
    n.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => n.remove(), 400);
  }, 3500);
}

function setMode(mode) {
  fetch('/api/set_mode', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: mode})})
    .then(r => r.json()).then(d => {
      if (d.success) {
        showNotification(d.message, 'success');
        updateModeUI();
        updateStatus();
      } else {
        showNotification('Hata: ' + d.message, 'error');
        updateModeUI();
      }
    }).catch(() => showNotification('Sunucu bağlantı hatası', 'error'));
}

function updateModeUI() {
  fetch('/api/status').then(r => r.json()).then(d => {
    var m = d.executor_mode || 'sim';
    var btnSim = document.getElementById('btnSim');
    var btnBin = document.getElementById('btnBinance');
    if (m === 'binance') {
      btnBin.className = 'btn text-[10px] font-extrabold px-3 py-1.5 rounded-md bg-blue-500/20 text-blue-400 border border-blue-500/30';
      btnSim.className = 'btn text-[10px] font-extrabold px-3 py-1.5 rounded-md text-gray-400 hover:text-white';
    } else {
      btnSim.className = 'btn text-[10px] font-extrabold px-3 py-1.5 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30';
      btnBin.className = 'btn text-[10px] font-extrabold px-3 py-1.5 rounded-md text-gray-400 hover:text-white';
    }
  }).catch(() => {});
}

function setSimCapital() {
  var inp = document.getElementById('simCapital');
  var val = parseFloat(inp.value);
  if (!val || val < 10) {
    alert('Simülasyon sermayesi en az 10 olmalı.');
    return;
  }
  fetch('/api/set_sim_capital', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount: val})})
    .then(r => r.json()).then(d => {
      if (d.success) showNotification(d.message, 'success');
      else showNotification('Hata: ' + d.message, 'error');
      setTimeout(updateStatus, 1000);
    }).catch(() => showNotification('Sunucu bağlantı hatası', 'error'));
}

function resetSim() {
  if (!confirm('Simülasyon sıfırlansın mı? Bakiye başlangıç sermayesine döner, pozisyon kapanır. (İşlem geçmişi KAYDEDİLİR, silinmez)')) return;
  fetch('/api/reset_sim', {method: 'POST'}).then(r => r.json()).then(d => {
    if (d.success) {
      showNotification(d.message, 'success');
      document.getElementById('simCapital').value = d.starting_capital;
      setTimeout(function() { updateStatus(); updateDecisions(); updateDailyPnl(); }, 1000);
    } else {
      showNotification('Hata: ' + d.message, 'error');
    }
  }).catch(() => showNotification('Sunucu bağlantı hatası', 'error'));
}

function testBinance() {
  var badge = document.getElementById('binanceStatusBadge');
  var txt = document.getElementById('binanceStatusText');
  txt.textContent = 'BINANCE: TEST...';
  badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-[10px] font-bold text-amber-400 cursor-pointer';
  fetch('/api/binance_status').then(r => r.json()).then(d => {
    if (d.connected) {
      var q = d.balance.quote, b = d.balance.base;
      txt.textContent = 'BINANCE: ✅ ' + Number(q).toLocaleString(undefined,{maximumFractionDigits:2});
      badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-[10px] font-bold text-emerald-400 cursor-pointer';
      showNotification('Binance bağlandı! Bakiye: ' + q.toFixed(2) + ' ' + (d.quote_asset||'USDT'), 'success');
    } else {
      txt.textContent = 'BINANCE: ❌ HATA';
      badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-[10px] font-bold text-rose-400 cursor-pointer';
      showNotification('Binance bağlantı hatası: ' + (d.error||'bilinmiyor'), 'error');
    }
  }).catch(() => {
    txt.textContent = 'BINANCE: ❌ BAĞLANTI';
    badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-[10px] font-bold text-rose-400 cursor-pointer';
    showNotification('Sunucu bağlantı hatası', 'error');
  });
}

function openBrainsEditor() {
  fetch('/api/brains').then(r => r.json()).then(d => {
    var html = '';
    Object.keys(d).forEach(function(key) {
      var b = d[key];
      html += '<div style="margin-bottom:18px">';
      html += '  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">';
      html += '    <label style="font-size:13px;font-weight:800;color:#e2e8f0">' + (b.icon||'🤖') + ' ' + (b.label||key) + '</label>';
      html += '    <label style="font-size:10px;color:#94a3b8;cursor:pointer"><input type="checkbox" id="enb_' + key + '" ' + (b.enabled!==false?'checked':'') + ' style="margin-right:4px">Aktif</label>';
      html += '  </div>';
      html += '  <textarea id="br_' + key + '" rows="4" style="width:100%;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:#e2e8f0;font-size:12px;padding:10px;resize:vertical;font-family:Inter,sans-serif">' + (b.instruction||'') + '</textarea>';
      html += '</div>';
    });
    document.getElementById('brainsModalBody').innerHTML = html;
    var modal = document.getElementById('brainsModal');
    modal.style.display = 'flex';
    setTimeout(function() { modal.classList.add('modal-visible'); }, 10);
  }).catch(() => showNotification('Beyin verileri alınamadı', 'error'));
}

function saveBrains() {
  fetch('/api/brains').then(r => r.json()).then(function(base) {
    var payload = {};
    Object.keys(base).forEach(function(key) {
      payload[key] = {
        instruction: document.getElementById('br_' + key).value,
        enabled: document.getElementById('enb_' + key).checked
      };
    });
    fetch('/api/brains', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)})
      .then(r => r.json()).then(d => {
        if (d.success) {
          showNotification('AI beyin talimatları kaydedildi ✅', 'success');
          closeBrainsModal();
        } else {
          showNotification('Kaydetme hatası: ' + d.message, 'error');
        }
      }).catch(() => showNotification('Sunucu bağlantı hatası', 'error'));
  });
}

function closeBrainsModal() {
  var modal = document.getElementById('brainsModal');
  modal.classList.remove('modal-visible');
  setTimeout(function() { modal.style.display = 'none'; }, 200);
}

function updateStatus() {
  fetch('/api/status').then(r => r.json()).then(d => {
    var badge = document.getElementById('statusBadge');
    if (d.running && !d.paused) {
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span><span>TARANIYOR...</span>';
      badge.className = 'flex items-center gap-2 px-3.5 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs font-bold text-emerald-400';
    } else if (d.paused) {
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-400"></span><span>DURAKLATILDI</span>';
      badge.className = 'flex items-center gap-2 px-3.5 py-1.5 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs font-bold text-amber-400';
    } else {
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-500"></span><span>PASİF</span>';
      badge.className = 'flex items-center gap-2 px-3.5 py-1.5 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs font-bold text-rose-400';
    }

    document.getElementById('sPortfolio').textContent = '$' + (d.portfolio_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('sCash').textContent = '$' + (d.cash || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('sScans').textContent = d.total_scans || 0;

    var pl = d.kar_zarar || 0;
    var plEl = document.getElementById('sPnl');
    plEl.textContent = '$' + (pl >= 0 ? '+' : '') + pl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    plEl.className = 'text-xl font-mono font-bold ' + (pl >= 0 ? 'text-emerald-400' : 'text-rose-400');

    var modeEl = document.getElementById('sMode');
    var m = d.executor_mode || 'sim';
    modeEl.textContent = m === 'binance' ? 'GERÇEK HESAP' : 'SİMÜLASYON';
    modeEl.className = 'text-base font-mono font-bold ' + (m === 'binance' ? 'text-emerald-400' : 'text-amber-400');

    var aiEl = document.getElementById('sAiAccuracy');
    if (d.ai_trained) {
      aiEl.innerHTML = '%' + (d.ai_accuracy * 100).toFixed(1) + ' <span class="text-[9px] text-slate-500 font-normal">(' + d.ai_prediction_count + 't)</span>';
    } else {
      aiEl.textContent = 'EĞİTİLİYOR...';
    }
  }).catch(() => {});

  fetch('/api/memory').then(r => r.json()).then(m => {
    var stats = m.stats || {};
    var scans = m.scans || [];
    var items = m.trades || [];

    document.getElementById('tradeCount').textContent = stats.toplam_islem || 0;

    var scanBody = document.getElementById('scanBody');
    if (scans.length > 0) {
      var sh = '';
      scans.forEach(function(s) {
        var actionBg = 'bg-slate-500/10 text-slate-400 border border-white/10';
        if (s.action === 'BUY') actionBg = 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
        if (s.action === 'SELL') actionBg = 'bg-rose-500/10 text-rose-400 border border-rose-500/20';
        
        var pctColor = s.confidence >= 0.6 ? 'text-emerald-400' : s.confidence <= 0.4 ? 'text-rose-400' : 'text-slate-400';
        
        sh += '<tr class="hover:bg-white/5 transition-colors border-b border-white/5">';
        sh += '<td class="px-5 py-3 text-slate-500">' + (s.time ? s.time.substring(11, 19) : '--') + '</td>';
        sh += '<td class="px-5 py-3 text-right font-semibold text-white">$' + Number(s.price).toLocaleString(undefined, {minimumFractionDigits: 2}) + '</td>';
        sh += '<td class="px-5 py-3 text-right text-slate-400">' + (s.rsi || 0).toFixed(1) + '</td>';
        sh += '<td class="px-5 py-3 text-center">' + (s.ema_cross === 'bullish' ? '<span class="text-emerald-400">🟢 UP</span>' : '<span class="text-rose-400">🔴 DOWN</span>') + '</td>';
        sh += '<td class="px-5 py-3 text-right text-slate-400">' + (s.macd_hist || 0).toFixed(2) + '</td>';
        sh += '<td class="px-5 py-3 text-center"><span class="px-2 py-0.5 rounded text-[10px] font-bold ' + actionBg + '">' + s.action + '</span></td>';
        sh += '<td class="px-5 py-3 text-right ' + pctColor + ' font-bold">' + (s.confidence * 100).toFixed(0) + '%</td>';
        
        var slog = s.system_log || '';
        var stratLabel = 'NORMAL';
        var stratColor = 'text-slate-500';
        if (slog.indexOf('STRICT') >= 0) { stratLabel = 'STRICT'; stratColor = 'text-blue-400 bg-blue-500/10 px-1 py-0.5 rounded'; }
        else if (slog.indexOf('AI') >= 0 || s.action !== 'HOLD') { stratLabel = 'AI SC'; stratColor = 'text-indigo-400 bg-indigo-500/10 px-1 py-0.5 rounded'; }
        
        sh += '<td class="px-5 py-3 text-center text-[10px] font-bold"><span class="' + stratColor + '">' + stratLabel + '</span></td>';
        
        var srcLabel = 'STRATEJİ';
        var srcColor = 'text-slate-600';
        if (slog.indexOf('STRICT+AI') >= 0) { srcLabel = 'STRICT+AI'; srcColor = 'text-blue-400'; }
        else if (slog.indexOf('STRICT') >= 0) { srcLabel = 'INDICATOR'; srcColor = 'text-cyan-400'; }
        else if (slog.indexOf('AI') >= 0 || s.action !== 'HOLD') { srcLabel = 'AI PRED'; srcColor = 'text-indigo-400'; }
        
        sh += '<td class="px-5 py-3 text-center ' + srcColor + ' text-[10px] font-bold">' + srcLabel + '</td></tr>';
      });
      scanBody.innerHTML = sh;
    } else {
      scanBody.innerHTML = '<tr><td colspan="9" class="px-5 py-8 text-center text-slate-500 italic">Veri bekleniyor...</td></tr>';
    }

    var tradeList = document.getElementById('tradeList');
    if (items.length > 0) {
      var html = '';
      items.forEach(function(t) {
        var actionColor = t.action === 'BUY' ? 'text-emerald-400' : 'text-rose-400';
        var actionBg = t.action === 'BUY' ? 'bg-emerald-500/10' : 'bg-rose-500/10';
        var time = t.time || '';
        if (time.length > 10) time = time.substring(11, 19);
        
        var modeBadge = t.mode === 'REAL' 
          ? '<span class="text-[8px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 font-extrabold">REAL</span>' 
          : '<span class="text-[8px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-extrabold">SIM</span>';
        
        var pnlStr = t.pnl !== 0 ? (t.pnl >= 0 ? '+' + t.pnl.toFixed(2) : t.pnl.toFixed(2)) : '---';
        var pnlColor = t.pnl > 0 ? 'text-emerald-400 bg-emerald-500/10' : t.pnl < 0 ? 'text-rose-400 bg-rose-500/10' : 'text-slate-400';
        var reasonStr = t.reason ? t.reason.substring(0, 20) : 'Algoritmik';
        
        html += '<div class="glass p-3 rounded-xl flex items-center justify-between text-xs font-mono trade-item">';
        html += '  <div class="flex items-center space-x-3">';
        html += '    <span class="text-slate-500">' + time + '</span>';
        html += '    <span class="font-bold px-2 py-0.5 rounded text-[10px] ' + actionBg + ' ' + actionColor + '">' + t.action + '</span>';
        html += '    ' + modeBadge;
        html += '  </div>';
        html += '  <div class="flex items-center space-x-3">';
        html += '    <span class="text-white font-semibold">$' + Number(t.price).toLocaleString(undefined, {minimumFractionDigits: 0}) + '</span>';
        html += '    <span class="text-[10px] text-slate-500 max-w-[90px] truncate">' + reasonStr + '</span>';
        html += '    <span class="px-2 py-0.5 rounded font-extrabold text-[10px] ' + pnlColor + '">' + (t.pnl !== 0 ? '$' + pnlStr : '---') + '</span>';
        html += '  </div>';
        html += '</div>';
      });
      tradeList.innerHTML = html;
    } else {
      tradeList.innerHTML = '<div class="glass p-6 rounded-xl text-center text-slate-500 text-xs">Henüz işlem geçmişi yok.</div>';
    }
  }).catch(() => {});
}

function updateDecisions() {
  fetch('/api/decisions').then(r => r.json()).then(d => {
    var dl = document.getElementById('decisionList');
    if (!dl) return;
    if (d.length === 0) {
      dl.innerHTML = '<div class="text-slate-500 italic text-center py-4 text-xs">Karar kaydı yok</div>';
      return;
    }
    var h = '';
    d.forEach(function(c) {
      var actColor = c.final_action === 'BUY' ? 'text-emerald-400' : c.final_action === 'SELL' ? 'text-rose-400' : 'text-slate-500';
      var vetoBadge = c.ai_veto ? '<span class="text-rose-400 text-[8px] bg-rose-500/10 px-1 py-0.5 rounded font-extrabold ml-1">VETO</span>' : '';
      var execBadge = c.executed ? '<span class="text-emerald-400 text-[9px] font-extrabold ml-1">✓</span>' : '';
      
      h += '<div class="flex justify-between items-center py-2 border-b border-white/5 hover:bg-white/5 px-2 rounded-lg transition-colors">';
      h += '  <span class="text-slate-500">' + (c.time ? c.time.substring(11, 19) : '--') + '</span>';
      h += '  <span class="' + actColor + ' font-bold">' + c.final_action + '</span>';
      h += '  <span class="text-slate-400">' + c.strategy_score.toFixed(1) + '/5</span>';
      h += '  <span class="text-slate-500 truncate max-w-[120px]">' + (c.strategy_reason || 'Piyasa İzleme') + '</span>';
      h += '  <span class="text-slate-400 font-mono font-bold">' + (c.ai_prob * 100).toFixed(0) + '%' + vetoBadge + execBadge + '</span>';
      h += '</div>';
    });
    dl.innerHTML = h;
  }).catch(() => {});
}

function updateGoal() {
  fetch('/api/status').then(r => r.json()).then(st => {
    var pv = st.portfolio_value || 0;
    fetch('/api/daily_pnl').then(r => r.json()).then(d => {
      var today = new Date().toISOString().slice(0, 10);
      var todays = (d || []).filter(function(g) { return g.date === today; });
      var pnl = todays.reduce(function(s, g) { return s + g.pnl; }, 0);
      var target = pv * 0.01;
      var pct = pv > 0 ? (pnl / pv * 100) : 0;
      var el = document.getElementById('goalText');
      var badge = document.getElementById('goalBadge');
      var sign = pnl >= 0 ? '+' : '';
      el.textContent = sign + pnl.toFixed(2) + '$ / HDF:' + target.toFixed(2) + '$ (' + pct.toFixed(2) + '%)';
      if (pct >= 1.0) {
        badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-emerald-500/15 border border-emerald-500/30 rounded-lg text-[10px] font-bold text-emerald-300';
      } else if (pnl < 0) {
        badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-[10px] font-bold text-rose-300';
      } else {
        badge.className = 'flex items-center gap-2 px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-[10px] font-bold text-indigo-300';
      }
    }).catch(() => {});
  }).catch(() => {});
}

function updateDailyPnl() {
  fetch('/api/daily_pnl').then(r => r.json()).then(d => {
    var dt = document.getElementById('dailyPnlTotal');
    if (!dt) return;
    if (!d || d.length === 0) {
      dt.textContent = 'İşlem yok';
      return;
    }
    var total = 0, totalWin = 0, totalLoss = 0;
    d.forEach(function(g) {
      total += g.pnl;
      if (g.pnl > 0) totalWin += g.pnl;
      else totalLoss += g.pnl;
    });
    dt.textContent = 'NET: ' + (total >= 0 ? '+' : '') + total.toFixed(2) + '$ | Win: ' + totalWin.toFixed(0) + '$ / Loss: ' + totalLoss.toFixed(0) + '$';
    
    var max = Math.max(...d.map(g => Math.abs(g.pnl)), 0.01);
    var ch = document.getElementById('dailyPnlChart');
    var h = '<div class="flex items-end justify-between gap-2.5 h-[140px] px-2 min-w-[280px]">';
    
    d.forEach(function(g) {
      var pct = Math.abs(g.pnl) / max * 100;
      var color = g.pnl >= 0 ? '#10b981' : '#ef4444';
      var barH = Math.max(pct, 6);
      
      h += '<div class="flex-1 flex flex-col items-center justify-end h-full group">';
      h += '  <span class="text-[9px] font-bold mb-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200" style="color:' + color + '">' + (g.pnl >= 0 ? '+' : '') + g.pnl.toFixed(0) + '</span>';
      h += '  <div class="w-full rounded-t-md opacity-80 hover:opacity-100 transition-all duration-300" style="height:' + barH + 'px; background:' + color + '; box-shadow: 0 0 10px ' + color + '33"></div>';
      h += '  <span class="text-[8px] text-slate-500 mt-2 font-mono whitespace-nowrap">' + g.date.slice(5) + '</span>';
      h += '</div>';
    });
    h += '</div>';
    ch.innerHTML = h;
  }).catch(() => {});
}

var _agentsData = null;
function updateAgents() {
  fetch('/api/agents').then(r => r.json()).then(d => {
    _agentsData = d;
    var cards = document.getElementById('agentCards');
    var ranking = document.getElementById('agentRanking');
    var badge = document.getElementById('consensusBadge');
    var rateEl = document.getElementById('consensusRate');
    if (!cards) return;

    var agentNames = {
      'trend': {label: 'Trend & Momentum', icon: '📈', gradient: 'from-blue-600 to-cyan-500'},
      'volatility': {label: 'Volatilite & RSI', icon: '📊', gradient: 'from-amber-500 to-orange-500'},
      'volume': {label: 'Hacim & Orderbook', icon: '📦', gradient: 'from-emerald-500 to-green-500'},
      'level': {label: 'Kırılım & Seviye', icon: '🎯', gradient: 'from-rose-500 to-pink-500'},
      'sentiment': {label: 'Duygu & Haber', icon: '🧠', gradient: 'from-purple-500 to-violet-500'}
    };

    var votes = d._last_votes || {};
    var coord = d._coordinator || {};

    // Konsensüs oranı
    if (coord.total_decisions > 0) {
      rateEl.textContent = 'KONSENSÜS ORANI: %' + (coord.consensus_rate * 100).toFixed(0) + ' (' + coord.total_decisions + ' karar)';
    }

    // Konsensüs badge
    var buyVotes = 0, sellVotes = 0;
    Object.values(votes).forEach(function(v) {
      if (v.action === 'BUY') buyVotes++;
      if (v.action === 'SELL') sellVotes++;
    });
    if (buyVotes >= 3) {
      badge.textContent = '🟢 AL (' + buyVotes + '/5)';
      badge.className = 'px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse';
    } else if (sellVotes >= 3) {
      badge.textContent = '🔴 SAT (' + sellVotes + '/5)';
      badge.className = 'px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse';
    } else {
      badge.textContent = '⚪ BEKLE';
      badge.className = 'px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-slate-500/10 text-slate-400 border border-white/10';
    }

    // Ajan kartları
    var h = '';
    var agentList = [];
    ['trend', 'volatility', 'volume', 'level', 'sentiment'].forEach(function(key) {
      var info = agentNames[key];
      var agent = d[key] || {};
      var vote = votes[key] || {};
      var vAction = vote.action || 'HOLD';
      var vConf = vote.confidence || 0;
      var vWeight = vote.weight || 1.0;

      var actionColor = vAction === 'BUY' ? 'text-emerald-400' : (vAction === 'SELL' ? 'text-rose-400' : 'text-slate-400');
      var actionBg = vAction === 'BUY' ? 'bg-emerald-500/15 border-emerald-500/30' : (vAction === 'SELL' ? 'bg-rose-500/15 border-rose-500/30' : 'bg-slate-500/10 border-white/10');
      var confBarColor = vAction === 'BUY' ? 'bg-emerald-500' : (vAction === 'SELL' ? 'bg-rose-500' : 'bg-slate-500');
      var confPct = Math.round(vConf * 100);
      var accPct = Math.round((agent.accuracy || 0) * 100);
      var trainBadge = agent.is_trained ? '<span class="text-[8px] px-1 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">AI</span>' : '<span class="text-[8px] px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">KURAL</span>';

      h += '<div class="glass rounded-xl p-3 border ' + (vAction !== 'HOLD' ? (vAction === 'BUY' ? 'border-emerald-500/20' : 'border-rose-500/20') : 'border-white/5') + ' transition-all duration-300 hover:scale-[1.02] hover:border-purple-500/40 cursor-pointer" onclick="showAgentDetail(`' + key + '`)">';
      h += '  <div class="flex items-center justify-between mb-2">';
      h += '    <span class="text-sm">' + info.icon + '</span>';
      h += '    ' + trainBadge;
      h += '  </div>';
      h += '  <h4 class="text-[10px] font-bold text-slate-300 mb-1">' + info.label + '</h4>';
      h += '  <div class="flex items-center justify-between mb-2">';
      h += '    <span class="text-sm font-extrabold ' + actionColor + '">' + (vAction === 'BUY' ? 'AL' : (vAction === 'SELL' ? 'SAT' : 'BEKLE')) + '</span>';
      h += '    <span class="text-[10px] font-mono font-bold ' + actionColor + '">' + confPct + '%</span>';
      h += '  </div>';
      h += '  <div class="w-full bg-surface-lowest rounded-full h-1.5 mb-2">';
      h += '    <div class="' + confBarColor + ' h-1.5 rounded-full transition-all duration-500" style="width:' + Math.max(confPct, 3) + '%"></div>';
      h += '  </div>';
      h += '  <div class="flex justify-between text-[9px] text-slate-500">';
      h += '    <span>Doğruluk: ' + accPct + '%</span>';
      h += '    <span>Ağırlık: ' + (agent.weight || 1.0).toFixed(1) + 'x</span>';
      h += '  </div>';
      h += '  <div class="text-center mt-1"><span class="text-[8px] text-slate-600">Detay için tıkla ▸</span></div>';
      h += '</div>';

      agentList.push({name: info.label, icon: info.icon, accuracy: agent.accuracy || 0, weight: agent.weight || 1.0, correct: agent.correct_predictions || 0, total: agent.total_predictions || 0});
    });
    cards.innerHTML = h;

    // Ranking
    if (ranking) {
      agentList.sort(function(a, b) { return b.accuracy - a.accuracy; });
      var rh = '';
      agentList.forEach(function(a, idx) {
        var barW = Math.max(a.accuracy * 100, 5);
        var barColor = a.accuracy > 0.6 ? 'bg-emerald-500' : (a.accuracy > 0.4 ? 'bg-amber-500' : 'bg-rose-500');
        rh += '<div class="flex items-center gap-2 py-1.5">';
        rh += '  <span class="text-[10px] text-slate-500 w-4 font-bold">#' + (idx+1) + '</span>';
        rh += '  <span class="text-sm w-5">' + a.icon + '</span>';
        rh += '  <span class="text-[10px] text-slate-300 font-bold w-24 truncate">' + a.name + '</span>';
        rh += '  <div class="flex-1 bg-surface-lowest rounded-full h-1.5">';
        rh += '    <div class="' + barColor + ' h-1.5 rounded-full transition-all" style="width:' + barW + '%"></div>';
        rh += '  </div>';
        rh += '  <span class="text-[10px] font-mono font-bold ' + (a.accuracy > 0.5 ? 'text-emerald-400' : 'text-slate-400') + ' w-10 text-right">%' + (a.accuracy * 100).toFixed(0) + '</span>';
        rh += '  <span class="text-[9px] text-slate-500 w-10 text-right">' + a.correct + '/' + a.total + '</span>';
        rh += '</div>';
      });
      ranking.innerHTML = rh;
    }
  }).catch(() => {});
}

// Initial updates
updateStatus();
updateModeUI();
testBinance();
updateGoal();
updateDecisions();
updateDailyPnl();
updateAgents();

// Polling intervals
setInterval(updateStatus, 5000);
setInterval(updateDecisions, 5000);
setInterval(updateDailyPnl, 10000);
setInterval(updateGoal, 15000);
setInterval(updateAgents, 5000);

// ==========================================
// GEMINI 5-BRAIN DEBATE PANEL
// ==========================================
var _geminiData = null;
function updateGemini() {
  fetch('/api/gemini_debate').then(r => r.json()).then(d => {
    _geminiData = d;
    var cards = document.getElementById('geminiBrainCards');
    var badge = document.getElementById('geminiFinalBadge');
    var statusEl = document.getElementById('geminiStatus');
    var summBox = document.getElementById('geminiSummaryBox');
    var summText = document.getElementById('geminiSummaryText');
    if (!cards) return;

    if (!d || !d.brains) {
      statusEl.textContent = 'API KEY GEREKLI';
      statusEl.className = 'text-[9px] font-mono text-amber-400 font-bold';
      cards.innerHTML = '<div class="text-slate-500 italic text-center py-6 text-xs col-span-5">Gemini API anahtarı .env dosyasına GEMINI_API_KEY olarak ekleyin</div>';
      return;
    }

    statusEl.textContent = 'CANLI DEBATE';
    statusEl.className = 'text-[9px] font-mono text-cyan-400 font-bold';

    var brainIcons = {'TREND': '📈', 'VOLATİLİTE': '📊', 'HACIM': '📦', 'SEVİYE': '🎯', 'DUYGU': '🧠'};
    var brainColors = {
      'TREND': 'from-blue-600 to-cyan-500',
      'VOLATİLİTE': 'from-amber-500 to-orange-500',
      'HACIM': 'from-emerald-500 to-green-500',
      'SEVİYE': 'from-rose-500 to-pink-500',
      'DUYGU': 'from-purple-500 to-violet-500'
    };

    // Final badge
    var fd = d.final_decision || 'HOLD';
    if (fd === 'BUY') {
      badge.textContent = '🟢 AL (' + (d.buy_count||0) + '/5)';
      badge.className = 'px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse';
    } else if (fd === 'SELL') {
      badge.textContent = '🔴 SAT (' + (d.sell_count||0) + '/5)';
      badge.className = 'px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse';
    } else {
      badge.textContent = '⚪ BEKLE';
      badge.className = 'px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-slate-500/10 text-slate-400 border border-white/10';
    }

    // Brain cards
    var h = '';
    d.brains.forEach(function(b) {
      var icon = brainIcons[b.name] || '🤖';
      var vAction = b.vote || 'HOLD';
      var vConf = Math.round((b.confidence || 0) * 100);
      var actionColor = vAction === 'BUY' ? 'text-emerald-400' : (vAction === 'SELL' ? 'text-rose-400' : 'text-slate-400');
      var actionBg = vAction === 'BUY' ? 'border-emerald-500/20' : (vAction === 'SELL' ? 'border-rose-500/20' : 'border-white/5');
      var confBarColor = vAction === 'BUY' ? 'bg-emerald-500' : (vAction === 'SELL' ? 'bg-rose-500' : 'bg-slate-500');
      var voteLabel = vAction === 'BUY' ? 'AL' : (vAction === 'SELL' ? 'SAT' : 'BEKLE');

      h += '<div class="glass rounded-xl p-3 border ' + actionBg + ' transition-all duration-300 hover:scale-[1.02]">';
      h += '  <div class="flex items-center justify-between mb-1.5">';
      h += '    <span class="text-sm">' + icon + '</span>';
      h += '    <span class="px-1.5 py-0.5 rounded text-[8px] font-extrabold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">GEMINI</span>';
      h += '  </div>';
      h += '  <h4 class="text-[10px] font-bold text-slate-300 mb-1">' + b.name + '</h4>';
      h += '  <div class="flex items-center justify-between mb-1.5">';
      h += '    <span class="text-sm font-extrabold ' + actionColor + '">' + voteLabel + '</span>';
      h += '    <span class="text-[10px] font-mono font-bold ' + actionColor + '">' + vConf + '%</span>';
      h += '  </div>';
      h += '  <div class="w-full bg-surface-lowest rounded-full h-1.5 mb-2">';
      h += '    <div class="' + confBarColor + ' h-1.5 rounded-full transition-all duration-500" style="width:' + Math.max(vConf, 3) + '%"></div>';
      h += '  </div>';
      h += '  <p class="text-[9px] text-slate-400 leading-relaxed line-clamp-3">' + (b.argument || '') + '</p>';
      h += '</div>';
    });
    cards.innerHTML = h;

    // Summary
    if (d.summary) {
      summBox.style.display = 'block';
      summText.textContent = d.summary;
    }
  }).catch(function() {
    var statusEl = document.getElementById('geminiStatus');
    if (statusEl) statusEl.textContent = 'BAĞLANTI HATASI';
  });
}

updateGemini();
setInterval(updateGemini, 8000);

// ==========================================
// AJAN DETAY MODALI
// ==========================================
function showAgentDetail(key) {
  if (!_agentsData) return;
  var modal = document.getElementById('agentDetailModal');
  var title = document.getElementById('modalTitle');
  var body = document.getElementById('modalBody');
  var scanData = _agentsData._last_scan_data || {};
  var news = _agentsData._last_news || [];
  var agent = _agentsData[key] || {};
  var vote = (_agentsData._last_votes || {})[key] || {};

  var names = {
    'trend': {label: 'Trend & Momentum', icon: '📈', ai: 'Random Forest Classifier'},
    'volatility': {label: 'Volatilite & RSI', icon: '📊', ai: 'SVM + KNN Ensemble'},
    'volume': {label: 'Hacim & Orderbook', icon: '📦', ai: 'Logistic Regression'},
    'level': {label: 'Kırılım & Seviye', icon: '🎯', ai: 'Gradient Boosting'},
    'sentiment': {label: 'Duygu & Haber', icon: '🧠', ai: 'VaderSentiment NLP + Decision Tree'}
  };
  var info = names[key] || {label: key, icon: '🤖', ai: '?'};

  title.innerHTML = info.icon + ' ' + info.label;

  var vAction = vote.action || 'HOLD';
  var vConf = Math.round((vote.confidence || 0) * 100);
  var acColor = vAction === 'BUY' ? '#34d399' : (vAction === 'SELL' ? '#fb7185' : '#94a3b8');
  var acText = vAction === 'BUY' ? 'AL' : (vAction === 'SELL' ? 'SAT' : 'BEKLE');

  var html = '';
  // Üst başlık bilgisi
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:12px;background:rgba(255,255,255,0.03);border-radius:12px;border:1px solid rgba(255,255,255,0.06)">';
  html += '  <div>';
  html += '    <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px">YAPAY ZEKA MOTORU</div>';
  html += '    <div style="font-size:13px;color:#e2e8f0;font-weight:800;margin-top:2px">' + info.ai + '</div>';
  html += '  </div>';
  html += '  <div style="text-align:right">';
  html += '    <div style="font-size:10px;color:#64748b;font-weight:700">KARAR</div>';
  html += '    <div style="font-size:18px;font-weight:900;color:' + acColor + '">' + acText + ' <span style="font-size:12px">%' + vConf + '</span></div>';
  html += '  </div>';
  html += '</div>';

  // Ajan Detay Tablosu
  html += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">📋 ANALİZ EDİLEN VERİLER</div>';
  html += '<div style="background:rgba(255,255,255,0.02);border-radius:10px;border:1px solid rgba(255,255,255,0.05);overflow:hidden">';

  if (key === 'trend') {
    var rows = [
      ['EMA 8', (scanData.ema8 || 0).toFixed(2)],
      ['EMA 21', (scanData.ema21 || 0).toFixed(2)],
      ['EMA Kesişim', scanData.ema_cross || 'yok'],
      ['EMA Mesafesi', (scanData.ema_dist || 0).toFixed(2) + '%'],
      ['MACD Histogram', (scanData.macd_hist || 0).toFixed(2)],
      ['MACD Önceki', (scanData.macd_hist_prev || 0).toFixed(2)],
      ['Fiyat Değişim (5bar)', (scanData.price_change_5 || 0).toFixed(2) + '%'],
      ['Hacim Oranı', (scanData.vol_ratio || 0).toFixed(2) + 'x'],
      ['ATR %', (scanData.atr_pct || 0).toFixed(2) + '%'],
    ];
    rows.forEach(function(r,i) {
      var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
      html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03)">';
      html += '  <span style="color:#94a3b8;font-size:11px">' + r[0] + '</span>';
      html += '  <span style="color:#e2e8f0;font-weight:700;font-size:11px;font-family:monospace">' + r[1] + '</span>';
      html += '</div>';
    });
  } else if (key === 'volatility') {
    var rows = [
      ['RSI (14)', (scanData.rsi || 0).toFixed(1)],
      ['RSI Önceki', (scanData.rsi_prev || 0).toFixed(1)],
      ['StochRSI', (scanData.stoch_rsi || 0).toFixed(1)],
      ['StochRSI Önceki', (scanData.stoch_rsi_prev || 0).toFixed(1)],
      ['Bollinger %B', (scanData.bb_pct || 0).toFixed(3)],
      ['BB Üst', '$' + (scanData.bb_upper || 0).toFixed(0)],
      ['BB Alt', '$' + (scanData.bb_lower || 0).toFixed(0)],
      ['ATR', '$' + (scanData.atr || 0).toFixed(2)],
      ['ATR %', (scanData.atr_pct || 0).toFixed(2) + '%'],
    ];
    rows.forEach(function(r,i) {
      var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
      var valColor = '#e2e8f0';
      if (r[0] === 'RSI (14)') {
        var rv = scanData.rsi || 50;
        if (rv < 30) valColor = '#34d399';
        else if (rv > 70) valColor = '#fb7185';
      }
      html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03)">';
      html += '  <span style="color:#94a3b8;font-size:11px">' + r[0] + '</span>';
      html += '  <span style="color:' + valColor + ';font-weight:700;font-size:11px;font-family:monospace">' + r[1] + '</span>';
      html += '</div>';
    });
  } else if (key === 'volume') {
    var ob = scanData.orderbook || {};
    var rows = [
      ['Hacim Oranı', (scanData.vol_ratio || 0).toFixed(2) + 'x'],
      ['Alıcı/Satıcı Oranı', (ob.bid_ask_ratio || 0).toFixed(3)],
      ['Orderbook Sinyali', ob.bid_ask_sinyal || 'notr'],
      ['Spread', '$' + (ob.spread || 0).toFixed(2)],
      ['Fiyat Değişim (5bar)', (scanData.price_change_5 || 0).toFixed(2) + '%'],
    ];
    rows.forEach(function(r,i) {
      var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
      html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03)">';
      html += '  <span style="color:#94a3b8;font-size:11px">' + r[0] + '</span>';
      html += '  <span style="color:#e2e8f0;font-weight:700;font-size:11px;font-family:monospace">' + r[1] + '</span>';
      html += '</div>';
    });
  } else if (key === 'level') {
    var rows = [
      ['Fiyat', '$' + (scanData.price || 0).toFixed(2)],
      ['Destek', '$' + (scanData.support || 0).toFixed(2)],
      ['Direnç', '$' + (scanData.resistance || 0).toFixed(2)],
      ['Yukarı Kırılım', scanData.breakout_up ? '🟢 EVET' : '❌ Hayır'],
      ['Aşağı Kırılım', scanData.breakout_down ? '🔴 EVET' : '❌ Hayır'],
      ['BB Üst', '$' + (scanData.bb_upper || 0).toFixed(0)],
      ['BB Alt', '$' + (scanData.bb_lower || 0).toFixed(0)],
    ];
    rows.forEach(function(r,i) {
      var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
      html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03)">';
      html += '  <span style="color:#94a3b8;font-size:11px">' + r[0] + '</span>';
      html += '  <span style="color:#e2e8f0;font-weight:700;font-size:11px;font-family:monospace">' + r[1] + '</span>';
      html += '</div>';
    });
  } else if (key === 'sentiment') {
    var sentAgent = _agentsData.sentiment || {};
    var fgVal = sentAgent.fear_greed || 50;
    var fgLabel = fgVal < 25 ? 'Aşırı Korku 😱' : (fgVal < 45 ? 'Korku 😰' : (fgVal < 55 ? 'Nötr 😐' : (fgVal < 75 ? 'Açgözlülük 🤑' : 'Aşırı Açgözlülük 🤯')));
    var fgColor = fgVal < 25 ? '#fb7185' : (fgVal < 45 ? '#f59e0b' : (fgVal < 55 ? '#94a3b8' : (fgVal < 75 ? '#34d399' : '#22d3ee')));

    html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:rgba(255,255,255,0.01);border-bottom:1px solid rgba(255,255,255,0.03)">';
    html += '  <span style="color:#94a3b8;font-size:11px">Sentiment Skoru</span>';
    html += '  <span style="color:#e2e8f0;font-weight:700;font-size:11px;font-family:monospace">' + (sentAgent.last_sentiment || 0).toFixed(3) + '</span>';
    html += '</div>';
    html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.03)">';
    html += '  <span style="color:#94a3b8;font-size:11px">Fear & Greed Index</span>';
    html += '  <span style="color:' + fgColor + ';font-weight:700;font-size:11px;font-family:monospace">' + fgVal + ' - ' + fgLabel + '</span>';
    html += '</div>';
  }
  html += '</div>';

  // Haberler (sadece sentiment için değil, hepsinde göster)
  if (key === 'sentiment' && news.length > 0) {
    html += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:16px 0 8px">📰 SON HABERLER (' + news.length + ')</div>';
    html += '<div style="max-height:220px;overflow-y:auto;background:rgba(255,255,255,0.02);border-radius:10px;border:1px solid rgba(255,255,255,0.05)">';
    news.forEach(function(n, i) {
      var sent = n.sentiment || 'notr';
      var sIcon = sent === 'pozitif' ? '🟢' : (sent === 'negatif' ? '🔴' : '⚪');
      var sColor = sent === 'pozitif' ? '#34d399' : (sent === 'negatif' ? '#fb7185' : '#94a3b8');
      var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
      html += '<div style="padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03);display:flex;gap:8px;align-items:flex-start">';
      html += '  <span style="font-size:12px;flex-shrink:0;margin-top:1px">' + sIcon + '</span>';
      html += '  <div style="flex:1;min-width:0">';
      html += '    <div style="font-size:11px;color:#cbd5e1;line-height:1.4;word-break:break-word">' + (n.baslik || n.title || 'Başlıksız') + '</div>';
      html += '    <div style="font-size:9px;color:' + sColor + ';font-weight:700;margin-top:2px">' + sent.toUpperCase() + '</div>';
      html += '  </div>';
      html += '</div>';
    });
    html += '</div>';
  } else if (key === 'sentiment' && news.length === 0) {
    html += '<div style="margin-top:12px;text-align:center;color:#475569;font-size:11px;padding:16px">Henüz haber taraması yapılmadı. Bot çalışmaya başlayınca haberler burada listelenecek.</div>';
  }

  // Ajan performansı
  html += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:16px 0 8px">📊 AJAN PERFORMANSI</div>';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">';
  html += '  <div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:10px;text-align:center;border:1px solid rgba(255,255,255,0.05)">';
  html += '    <div style="font-size:9px;color:#64748b">Doğruluk</div>';
  html += '    <div style="font-size:16px;font-weight:900;color:#e2e8f0;font-family:monospace">%' + Math.round((agent.accuracy || 0) * 100) + '</div>';
  html += '  </div>';
  html += '  <div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:10px;text-align:center;border:1px solid rgba(255,255,255,0.05)">';
  html += '    <div style="font-size:9px;color:#64748b">Ağırlık</div>';
  html += '    <div style="font-size:16px;font-weight:900;color:#e2e8f0;font-family:monospace">' + (agent.weight || 1.0).toFixed(2) + 'x</div>';
  html += '  </div>';
  html += '  <div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:10px;text-align:center;border:1px solid rgba(255,255,255,0.05)">';
  html += '    <div style="font-size:9px;color:#64748b">Tahmin</div>';
  html += '    <div style="font-size:16px;font-weight:900;color:#e2e8f0;font-family:monospace">' + (agent.correct_predictions || 0) + '/' + (agent.total_predictions || 0) + '</div>';
  html += '  </div>';
  html += '</div>';

  body.innerHTML = html;
  modal.style.display = 'flex';
  setTimeout(function() { modal.classList.add('modal-visible'); }, 10);
}

function closeAgentModal() {
  var modal = document.getElementById('agentDetailModal');
  modal.classList.remove('modal-visible');
  setTimeout(function() { modal.style.display = 'none'; }, 200);
}

</script>

<!-- AI BEYİNLERİ DÜZENLEME MODALI -->
<div id="brainsModal" onclick="if(event.target===this)closeBrainsModal()" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);z-index:9999;justify-content:center;align-items:center;opacity:0;transition:opacity 0.2s ease">
  <div style="background:linear-gradient(135deg,#0f172a 0%,#0c1a2e 100%);border-radius:20px;border:1px solid rgba(255,255,255,0.1);max-width:640px;width:92%;max-height:88vh;overflow-y:auto;padding:24px;box-shadow:0 25px 50px rgba(0,0,0,0.5)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <h3 style="font-size:18px;font-weight:900;color:white;margin:0">🧠 AI Beyinlerini Düzenle</h3>
      <button onclick="closeBrainsModal()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#94a3b8;font-size:16px;width:32px;height:32px;cursor:pointer;display:flex;align-items:center;justify-content:center">✕</button>
    </div>
    <p style="font-size:11px;color:#64748b;margin-bottom:14px;line-height:1.4">Her analiz bölümü için AI'ın nasıl düşüneceğini yaz. Bu talimatlar Gemini 5-Beyin tartışmasında kullanılır. İstediğin bilgiyi sen yazabilirsin.</p>
    <div id="brainsModalBody"></div>
    <div style="display:flex;gap:10px;margin-top:18px">
      <button onclick="saveBrains()" style="flex:1;background:linear-gradient(135deg,#06b6d4,#3b82f6);color:white;font-weight:800;font-size:13px;padding:12px;border-radius:12px;border:none;cursor:pointer">💾 KAYDET</button>
      <button onclick="closeBrainsModal()" style="background:rgba(255,255,255,0.06);color:#94a3b8;font-weight:700;font-size:13px;padding:12px 18px;border-radius:12px;border:1px solid rgba(255,255,255,0.1);cursor:pointer">İPTAL</button>
    </div>
  </div>
</div>

<!-- AJAN DETAY MODALI -->
<div id="agentDetailModal" onclick="if(event.target===this)closeAgentModal()" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);z-index:9999;justify-content:center;align-items:center;opacity:0;transition:opacity 0.2s ease">
  <div style="background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);border-radius:20px;border:1px solid rgba(255,255,255,0.1);max-width:520px;width:90%;max-height:85vh;overflow-y:auto;padding:24px;box-shadow:0 25px 50px rgba(0,0,0,0.5)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 id="modalTitle" style="font-size:18px;font-weight:900;color:white;margin:0"></h3>
      <button onclick="closeAgentModal()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#94a3b8;font-size:16px;width:32px;height:32px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s" onmouseover="this.style.background='rgba(255,255,255,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'">✕</button>
    </div>
    <div id="modalBody"></div>
  </div>
</div>
<style>.modal-visible{opacity:1!important}</style>
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
        from src.executor import executor
        data = request.get_json()
        amount = float(data.get('amount', 0))
        if amount <= 0:
            return jsonify({"success": False, "message": "Geçersiz miktar"})
        result = executor.buy(amount_usd=amount)
        if result and result.get("error") == "PERMISSION":
            return jsonify({"success": False, "message": result.get("message", "Binance işlem yetkisi yok")})
        if result:
            db.save_trade("BUY", result["price"], result["qty"], 0, "Manuel Islem", result["price"], result.get("mode", "SIM"))
            tg.send(f"🟢 <b>MANUEL ALIS GERCEKLESTIRILDI</b>\n\nFiyat: <code>${result['price']:,.2f}</code>\nMiktar: <code>{result['qty']:.6f} BTC</code>\nTutar: <code>${amount:.2f}</code>\nMod: <b>{result.get('mode', 'SIM')}</b>")
            return jsonify({"success": True, "message": f"{amount} USDT değerinde alım yapıldı ({result.get('mode', 'SIM')})"})
        else:
            return jsonify({"success": False, "message": "Alım başarısız"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/manual_sell', methods=['POST'])
def api_manual_sell():
    try:
        from src.executor import executor
        # Sells the entire BTC position
        result = executor.sell()
        if result and result.get("error") == "PERMISSION":
            return jsonify({"success": False, "message": result.get("message", "Binance işlem yetkisi yok")})
        if result:
            pl = result.get("pl", 0)
            mode = result.get("mode", "SIM")
            quant_agent.islem_sonucu_kaydet(pl)
            db.save_trade("SELL", result["price"], result["qty"], pl, "Manuel Satis", quant_agent.state.get("son_giris_fiyati", 0), mode)
            tg.send(f"🔴 <b>MANUEL SATIS GERCEKLESTIRILDI</b>\n\nFiyat: <code>${result['price']:,.2f}</code>\nMiktar: <code>{result['qty']:.6f} BTC</code>\nKar/Zarar: <b>${pl:+,.2f}</b>\nMod: <b>{mode}</b>")
            return jsonify({"success": True, "message": f"Satım yapıldı ({mode})"})
        else:
            return jsonify({"success": False, "message": "Satılacak pozisyon bulunamadı veya satım başarısız"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/debug')
def api_debug():
    import os
    db_exists = os.path.exists("trades.db")
    db_size = os.path.getsize("trades.db") if db_exists else 0
    env_keys = {k: v[:10] + "..." if v and k.endswith(("KEY", "TOKEN", "SECRET")) else v for k, v in os.environ.items() if k.startswith(("BINANCE", "TELEGRAM"))}
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

@app.route('/api/agents')
def api_agents():
    """5 AI ajanının durumlarını ve oylarını döndür."""
    state = quant_agent.get_consensus_state()
    from src.bot import bot
    state["_last_scan_data"] = bot.last_scan_data if hasattr(bot, 'last_scan_data') else {}
    state["_last_news"] = bot.last_news if hasattr(bot, 'last_news') else []
    return jsonify(state)

@app.route('/api/keepalive')
def api_keepalive():
    return ("", 200)

@app.route('/api/gemini_debate')
def api_gemini_debate():
    """Gemini 5-Brain AI tartışma sonucunu döndür."""
    from src import llm_agent
    debate = llm_agent.get_last_debate()
    if debate:
        return jsonify(debate)
    return jsonify({})


@app.route('/api/set_mode', methods=['POST'])
def api_set_mode():
    from src.executor import executor
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'sim')
    result = executor.set_mode(mode)
    if result.get('success'):
        return jsonify({"success": True, "message": result.get('message', 'Mod değişti'), "executor_mode": settings.executor_mode})
    return jsonify({"success": False, "message": result.get('message', 'Mod değiştirilemedi')})


@app.route('/api/set_sim_capital', methods=['POST'])
def api_set_sim_capital():
    from src.executor import executor
    data = request.get_json(silent=True) or {}
    amount = float(data.get('amount', 500))
    result = executor.reset_sim_balance(amount)
    if result.get('success'):
        return jsonify({"success": True, "message": result.get('message'), "balance": result.get('balance')})
    return jsonify({"success": False, "message": result.get('message', 'Ayarlanamadı')})


@app.route('/api/reset_sim', methods=['POST'])
def api_reset_sim():
    from src.executor import executor
    result = executor.reset_sim()
    if result.get('success'):
        try:
            from src.database import db
            from src.trader import trader
            price = trader.get_price() if settings.executor_mode == "binance" else 0
            db.save_decision(
                strategy_action="RESET", strategy_score=0.0,
                strategy_reason="Simülasyon başlangıç sermayesine sıfırlandı",
                ai_prob=0.0, ai_veto=False, final_action="RESET",
                final_reason="Kullanıcı simülasyonu sıfırladı", price=price, executed=0,
            )
        except Exception as e:
            print(f"[RESET] kayit hatasi: {e}")
        return jsonify({"success": True, "message": result.get('message'), "starting_capital": result.get('starting_capital')})
    return jsonify({"success": False, "message": result.get('message', 'Sıfırlanamadı')})


@app.route('/api/binance_status')
def api_binance_status():
    from src.executor import executor
    res = executor.test_binance_connection()
    res['executor_mode'] = settings.executor_mode
    res['quote_asset'] = settings.quote_asset
    return jsonify(res)


@app.route('/api/brains', methods=['GET'])
def api_get_brains():
    from src import ai_brains
    return jsonify(ai_brains.load_brains())


@app.route('/api/brains', methods=['POST'])
def api_post_brains():
    from src import ai_brains
    data = request.get_json(silent=True) or {}
    try:
        for key, val in data.items():
            ai_brains.update_brain(
                key,
                instruction=val.get('instruction'),
                enabled=val.get('enabled'),
                label=val.get('label'),
            )
        return jsonify({"success": True, "message": "Kaydedildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


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
