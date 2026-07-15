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
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<script>
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        surface: {
          DEFAULT: '#121318',
          dim: '#1a1b21',
          bright: '#292a2f',
          lowest: '#0d0e13',
          low: '#1e1f25',
        },
        trading: {
          buy: '#00e1ab',
          sell: '#cb0247',
          accent: '#3ad6ff'
        },
        // ─── Cyber-Quant Pro: varsayılan Tailwind renklerini yeniden eşle ───
        emerald: { 300: '#7dffdc', 400: '#2ee6b4', 500: '#00e1ab', 600: '#00c295' },
        rose:    { 300: '#ffc7cd', 400: '#ffb2ba', 500: '#cb0247', 600: '#a3023b' },
        red:     { 400: '#ffb2ba', 500: '#cb0247' },
        indigo:  { 300: '#7ee7ff', 400: '#3ad6ff', 500: '#22b8e6', 600: '#1aa0cc' },
        blue:    { 300: '#7ee7ff', 400: '#3ad6ff', 500: '#22b8e6', 600: '#1aa0cc' },
        cyan:    { 400: '#3ad6ff', 500: '#22b8e6' },
        purple:  { 200: '#e9dcff', 300: '#cbb6ff', 400: '#a87bff', 500: '#7727ff', 600: '#5e1fcf' },
        violet:  { 500: '#7727ff' },
        green:   { 500: '#00e1ab' },
        amber:   { 300: '#ffd58a', 400: '#ffb84d', 500: '#f59e0b', 600: '#b45309' },
        yellow:  { 500: '#ffb84d' },
        slate:   { 200: '#cdd3da', 300: '#9aa3ad', 400: '#83958c', 500: '#5b636e', 600: '#3a4a43' }
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
  font-family: 'Geist', 'Inter', sans-serif;
  background: #0A0B10;
  color: #e3e1e9;
  min-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
  -webkit-tap-highlight-color: transparent;
}
.glass {
  background: #14161f;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid #232634;
  /* Tonal layering + inner glow (drop-shadow yerine) */
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
}
.glass-glow {
  box-shadow: inset 0 0 0 1px rgba(0, 225, 171, 0.10), 0 0 18px rgba(0, 225, 171, 0.06);
}
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: #0d0e13;
}
::-webkit-scrollbar-thumb {
  background: #3a4a43;
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #83958c;
}
@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 5px rgba(0, 225, 171, 0.25); }
  50% { box-shadow: 0 0 14px rgba(0, 225, 171, 0.55); }
}
.pulse-glow-green {
  animation: pulse-glow 2s infinite;
}
.btn {
  transition: filter 0.2s ease, transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.btn:hover {
  filter: brightness(1.1);
}
.btn:active {
  transform: translateY(1px);
  filter: brightness(0.95);
}
.trade-item {
  transition: all 0.2s ease;
}
.trade-item:hover {
  background: rgba(255, 255, 255, 0.03);
  transform: translateX(2px);
}
.tradingview-widget-container.tv-fs {
  position: fixed;
  inset: 0;
  z-index: 9998;
  height: 100vh !important;
  width: 100vw !important;
  background: #020617;
  border-radius: 0 !important;
}
.tradingview-widget-container.tv-fs #tradingview_chart {
  height: 100vh !important;
}
.tradingview-widget-container.tv-fs iframe {
  width: 100% !important;
  height: 100% !important;
  border: none !important;
}
.agent-inline-detail { animation: slideDown 0.25s ease; }
@keyframes slideDown {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
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

    <!-- Mod (yalnızca simülasyon) -->
    <div class="flex items-center gap-1 bg-surface-lowest border border-white/10 rounded-lg px-3 py-1.5">
      <span class="text-[10px] font-extrabold text-amber-400 border border-amber-500/30 bg-amber-500/20 px-2 py-1 rounded-md">🟡 SİMÜLASYON</span>
    </div>

    <div class="flex items-center gap-2">
      <button onclick="manualBuy()" class="btn bg-trading-buy hover:bg-emerald-600 text-white text-xs font-extrabold px-4 py-2 rounded-lg shadow-lg shadow-emerald-500/20">
        AL
      </button>
      <button onclick="manualSell()" class="btn bg-trading-sell hover:bg-rose-600 text-white text-xs font-extrabold px-4 py-2 rounded-lg shadow-lg shadow-rose-500/20">
        SAT
      </button>
    </div>

    <!-- Sistem Kontrolleri -->
    <div class="flex items-center gap-2 bg-surface-lowest border border-white/5 rounded-lg p-1">
      <button id="btnStart" onclick="startBot()" class="btn text-[10px] font-bold text-gray-400 hover:text-white px-2.5 py-1 rounded">START</button>
      <button id="btnStop" onclick="stopBot()" class="btn text-[10px] font-bold text-gray-400 hover:text-white px-2.5 py-1 rounded">STOP</button>
      <button onclick="resetAll()" class="btn text-[10px] font-bold text-rose-300 hover:text-white px-2.5 py-1 rounded border border-rose-500/30" title="Simülasyonu baştan sona sıfırla">TAM SIFIRLA</button>
      <button onclick="scanNow()" class="btn bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold px-3 py-1 rounded-md shadow-md shadow-blue-500/10">
        TARA
      </button>
    </div>

    <div class="font-mono text-sm text-slate-400 bg-surface-lowest px-3 py-1.5 border border-white/5 rounded-lg" id="clock">--:--:--</div>

    <!-- USD/TRY Kuru -->
    <div id="fxBadge" class="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-[10px] font-bold text-emerald-300" title="Canlı döviz kuru (1$ = ?₺)">
      <span>💱</span><span id="fxText">$1 = ₺--</span>
    </div>

    <!-- Günlük Hedef %1 Takipçisi -->
    <div id="goalBadge" class="flex items-center gap-2 px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-[10px] font-bold text-indigo-300" title="Günlük %1 hedefi">
      <span>🎯 HEDEF</span><span id="goalText">--</span>
    </div>
  </div>
</header>

<main class="p-6 space-y-6 w-full">

  <!-- CANLI GRAFİK (üstte) -->
  <section class="glass rounded-2xl overflow-hidden glass-glow">
    <div class="px-5 py-4 border-b border-white/5 flex items-center justify-between bg-surface-lowest/40">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span> Canlı Fiyat Grafiği (BTC/USD)
      </h3>
      <div class="flex items-center gap-2">
        <div class="flex items-center gap-1 bg-surface-lowest border border-white/10 rounded-lg p-0.5">
          <button onclick="changeInterval('1')" class="btn text-[10px] font-bold px-2.5 py-1 rounded text-slate-300 hover:text-white" id="iv1">1dk</button>
          <button onclick="changeInterval('5')" class="btn text-[10px] font-bold px-2.5 py-1 rounded bg-blue-500/20 text-blue-300" id="iv5">5dk</button>
          <button onclick="changeInterval('15')" class="btn text-[10px] font-bold px-2.5 py-1 rounded text-slate-300 hover:text-white" id="iv15">15dk</button>
        </div>
        <button onclick="toggleChartFullscreen()" class="btn bg-slate-600 hover:bg-slate-500 text-white text-[10px] font-bold px-3 py-1.5 rounded-md" title="GraFiği büyüt">⛶ BÜYÜT</button>
      </div>
    </div>
    <div class="tradingview-widget-container w-full h-[380px]" id="tradingviewWrap">
      <div id="tradingview_chart" class="w-full h-full"></div>
    </div>
  </section>

  <!-- 5 AI AJAN TREND KONSENSÜS PANELİ -->
  <section class="glass rounded-2xl p-5 glass-glow border border-purple-500/10" data-purpose="ai-consensus-panel">
    <div class="border-b border-white/5 pb-3 mb-4 flex items-center justify-between">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span> 5 AI Ajan Konsensüs Sistemi (TREND)
      </h3>
      <div class="flex items-center gap-3">
        <span class="text-[10px] font-mono text-purple-400 font-bold" id="consensusRate">---</span>
        <span id="consensusBadge" class="px-2.5 py-1 rounded-lg text-[10px] font-extrabold bg-slate-500/10 text-slate-400 border border-white/10">BEKLE</span>
      </div>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-5 gap-3" id="agentCards">
      <div class="text-slate-500 italic text-center py-6 text-xs col-span-5">Ajan verileri yükleniyor...</div>
    </div>

    <!-- TREND kartına basınca açılan inline panel -->
    <div id="agentDetailInline" style="display:none" class="mt-4 pt-4 border-t border-white/5 agent-inline-detail"></div>

    <!-- AI YÖNET (5 beyne prompt ile eğit) -->
    <div class="mt-4 pt-4 border-t border-white/5" data-purpose="ai-manage">
      <div class="flex items-center justify-between mb-2">
        <button onclick="toggleAiManage()" class="flex items-center gap-2 text-[11px] font-bold text-purple-300 hover:text-purple-200">
          <span id="aiManageChevron">▸</span> 🤖 AI YÖNET — 5 beyne talimat ver / eğit
        </button>
        <button onclick="openBrainsEditor()" class="btn text-[9px] font-bold px-2.5 py-1 rounded-md bg-purple-500/15 text-purple-300 border border-purple-500/30 hover:bg-purple-500/25">⚙️ BEYİNLERİ DÜZENLE</button>
      </div>
      <div id="aiManageBox" style="display:none">
        <p class="text-[10px] text-slate-500 mb-2 leading-relaxed">Buraya yazdığın talimat 5 beynin tamamına <b>üstten bağlayıcı rehber</b> olarak eklenir. Örn: "Sadece güçlü trendlerde işlem yap, gereksiz risk alma." Kaydettikten sonra sıradaki tartışmada uygulanır.</p>
        <textarea id="directiveInput" rows="3" placeholder="5 beyne vermek istediğin eğitim talimatı / strateji notu..." class="w-full bg-surface-lowest/60 border border-white/10 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-purple-500/40 resize-none"></textarea>
        <div class="flex items-center justify-between mt-2">
          <span id="directiveStatus" class="text-[10px] text-emerald-400"></span>
          <button onclick="trainDirective()" class="btn bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-extrabold px-3 py-1.5 rounded-md shadow-md shadow-purple-500/10">EĞİT / KAYDET</button>
        </div>
        <div class="mt-3 pt-3 border-t border-white/5">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[10px] font-bold text-slate-400">SON BESLEME (beynlere gidiyor)</span>
            <button onclick="updateReflection()" class="text-[9px] text-purple-300 hover:text-purple-200">YENİLE</button>
          </div>
          <div id="reflectionBox" class="text-[10px] text-slate-400 bg-surface-lowest/60 border border-white/5 rounded-lg p-2.5 leading-relaxed mb-2">Hesaplanıyor...</div>
          <div id="lastDebateBox" class="grid grid-cols-5 gap-1.5"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- HABERLER AKIŞI -->
  <section class="glass rounded-2xl p-5 border border-amber-500/10">
    <div class="border-b border-white/5 pb-3 mb-3 flex items-center justify-between">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> 📰 Bitcoin Haberleri
      </h3>
      <span class="text-[10px] font-mono text-amber-400">ÜZERİNE BASINCA HABER AÇILIR</span>
    </div>
    <div id="newsFeed" class="space-y-2 max-h-[260px] overflow-y-auto scrollbar">
      <div class="text-slate-500 italic text-center py-4 text-xs">Haber yükleniyor...</div>
    </div>
  </section>

  <!-- Ana Metrik Kartları -->
  <section class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4" data-purpose="top-stats-cards">
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">PORTFÖY DEĞERİ</span>
      <h2 class="text-xl font-extrabold font-mono text-white mt-1" id="sPortfolio">₺0</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">KULLANILABİLİR NAKİT</span>
      <h2 class="text-xl font-extrabold font-mono text-white mt-1" id="sCash">₺0</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">NET K/Z</span>
      <h2 class="text-xl font-extrabold font-mono mt-1" id="sPnl">₺+0,00</h2>
    </div>
    <div class="glass p-4 rounded-xl flex flex-col justify-between">
      <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">HESAP MODU</span>
      <h2 class="text-base font-extrabold font-mono mt-1 text-amber-400" id="sMode">SİMÜLASYON</h2>
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

  <!-- Grafik ve Karar Kayıtları Grid -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Sol ve Orta Kolon (Sonuç Tablosu) -->
    <div class="lg:col-span-2 space-y-6 flex flex-col">
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

      <!-- Analitik Performans -->
      <section class="glass rounded-2xl flex flex-col p-5 border border-cyan-500/10">
        <div class="border-b border-white/5 pb-3 mb-3 flex items-center justify-between">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-cyan-500"></span> Analitik Performans
          </h3>
          <span class="text-[10px] font-mono text-cyan-400">MATEMATİKSEL METRİK</span>
        </div>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="bg-surface-lowest/60 rounded-lg p-2 text-center">
            <div class="text-[9px] text-slate-500 font-bold uppercase">BEKLENTİ (₺)</div>
            <div class="text-base font-extrabold font-mono text-white" id="aExpectancy">--</div>
          </div>
          <div class="bg-surface-lowest/60 rounded-lg p-2 text-center">
            <div class="text-[9px] text-slate-500 font-bold uppercase">PROFIT FACTOR</div>
            <div class="text-base font-extrabold font-mono text-white" id="aProfitFactor">--</div>
          </div>
          <div class="bg-surface-lowest/60 rounded-lg p-2 text-center">
            <div class="text-[9px] text-slate-500 font-bold uppercase">KAZANMA %</div>
            <div class="text-base font-extrabold font-mono text-white" id="aWinRate">--</div>
          </div>
          <div class="bg-surface-lowest/60 rounded-lg p-2 text-center">
            <div class="text-[9px] text-slate-500 font-bold uppercase">MAX DRAWDD %</div>
            <div class="text-base font-extrabold font-mono text-white" id="aMaxDD">--</div>
          </div>
        </div>
        <div class="text-[10px] text-slate-500 mb-1 font-bold uppercase">EQUITY EĞRİSİ</div>
        <svg id="equitySpark" viewBox="0 0 200 50" preserveAspectRatio="none" class="w-full h-12 bg-surface-lowest/40 rounded"></svg>
        <div class="text-[10px] text-slate-500 mt-2" id="aMeta">İşlem yok.</div>
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

      <!-- OTONOM ÖĞRENME -->
      <section class="glass rounded-2xl flex flex-col p-5 border border-emerald-500/10">
        <div class="border-b border-white/5 pb-3 mb-3 flex justify-between items-center">
          <h3 class="text-sm font-bold text-white flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> 🧠 Otonom Öğrenme
          </h3>
          <span class="text-[10px] font-mono text-emerald-400">SİSTEM KENDİNİ GELİŞTİRİYOR</span>
        </div>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="bg-surface-lowest/60 rounded-lg p-2 text-center">
            <div class="text-[9px] text-slate-500 font-bold uppercase">İŞLEM AGR.</div>
            <div class="text-sm font-extrabold font-mono text-emerald-400" id="siAgg">1.00x</div>
          </div>
          <div class="bg-surface-lowest/60 rounded-lg p-2 text-center">
            <div class="text-[9px] text-slate-500 font-bold uppercase">GÜVEN EŞİĞİ</div>
            <div class="text-sm font-extrabold font-mono text-cyan-400" id="siConf">0.45</div>
          </div>
        </div>
        <div class="text-[10px] text-slate-500 font-bold uppercase tracking-wider mb-1">SON ÖĞRENİLEN DERSLER</div>
        <div class="space-y-1.5 max-h-[160px] overflow-y-auto scrollbar text-[10px] font-mono" id="siLessons">
          <div class="text-slate-500 italic text-center py-4">Henüz ders yok</div>
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

  <!-- Sadece Kâr/Zarar Gösterimi -->
  <section class="glass rounded-2xl p-5" data-purpose="pnl-history">
    <div class="border-b border-white/5 pb-3 mb-4 flex items-center justify-between">
      <h3 class="text-sm font-bold text-white flex items-center gap-2">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Kâr / Zarar Geçmişi
      </h3>
      <div class="flex items-center gap-3 text-[10px] font-mono">
        <span class="text-amber-400/80 hidden sm:inline">ÜZERİNE BASINCA DETAY AÇILIR 🔍</span>
        <span class="text-emerald-400">TOPLAM K/Z: <b id="pnlTotal">₺0,00</b></span>
        <span class="text-slate-500">İşlem: <b id="pnlCount">0</b></span>
      </div>
    </div>
    <div id="pnlHistory" class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
      <div class="col-span-full text-slate-500 italic text-center py-6 text-xs">Henüz işlem yok</div>
    </div>
  </section>
</main>

<script src="https://s3.tradingview.com/tv.js"></script>
<script>
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('tr-TR');
}, 1000);

// ─── TR (₺) gösterimi ───
let TRY_RATE = 32.0;
function tryFmt(usd) {
  var neg = (usd || 0) < 0;
  var v = Math.abs(usd || 0) * TRY_RATE;
  return (neg ? '-₺' : '₺') + v.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function tryShort(usd) {
  var neg = (usd || 0) < 0;
  var v = Math.abs(usd || 0) * TRY_RATE;
  if (v === 0) return '₺0';
  return (neg ? '-₺' : '+₺') + v.toLocaleString('tr-TR', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
function localToday() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function loadFx() {
  fetch('/api/fx').then(r => r.json()).then(d => {
    if (d.usd_try) TRY_RATE = d.usd_try;
    var el = document.getElementById('fxText');
    if (el) el.textContent = '$1 = ₺' + TRY_RATE.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }).catch(() => {});
}

// ─── Canlı grafik (TradingView) kontrolü ───
let tvWidget = null;
function createChart(interval) {
  var el = document.getElementById('tradingview_chart');
  if (!el) return;
  el.innerHTML = '';
  if (tvWidget && tvWidget.remove) { try { tvWidget.remove(); } catch (e) {} }
  if (typeof TradingView === 'undefined') { setTimeout(function () { createChart(interval); }, 800); return; }
  tvWidget = new TradingView.widget({
    "width": "100%",
    "height": "100%",
    "symbol": "COINBASE:BTCUSD",
    "interval": interval,
    "timezone": "Europe/Istanbul",
    "theme": "dark",
    "style": "1",
    "locale": "tr",
    "toolbar_bg": "#0e1424",
    "enable_publishing": false,
    "hide_side_toolbar": false,
    "allow_symbol_change": true,
    "autosize": true,
    "container_id": "tradingview_chart"
  });
  ['iv1', 'iv5', 'iv15'].forEach(function (id) {
    var b = document.getElementById(id);
    if (b) b.className = 'btn text-[10px] font-bold px-2.5 py-1 rounded text-slate-300 hover:text-white';
  });
  var a = document.getElementById('iv' + interval);
  if (a) a.className = 'btn text-[10px] font-bold px-2.5 py-1 rounded bg-blue-500/20 text-blue-300';
}
function changeInterval(tf) { createChart(tf); }
function toggleChartFullscreen() {
  var c = document.getElementById('tradingviewWrap');
  if (c.classList.contains('tv-fs')) c.classList.remove('tv-fs');
  else c.classList.add('tv-fs');
  // TradingView iframe'inin yeni boyuta uyum sağlaması için resize event'i tetikle
  setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 50);
  setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 350);
}

// ─── TREND kartına basınca açılan inline panel ───
let _openAgentKey = null;
function toggleAgentInline(key) {
  var box = document.getElementById('agentDetailInline');
  if (!box) return;
  if (_openAgentKey === key && box.style.display !== 'none') {
    box.style.display = 'none';
    _openAgentKey = null;
    return;
  }
  _openAgentKey = key;
  box.innerHTML = agentInlineHTML(key);
  box.style.display = 'block';
}
function agentInlineHTML(key) {
  if (!_agentsData) return '';
  var scanData = _agentsData._last_scan_data || {};
  var news = _agentsData._last_news || [];
  var agent = _agentsData[key] || {};
  var vote = (_agentsData._last_votes || {})[key] || {};
  var names = {
    'trend': {label: 'Trend & Momentum', icon: '📈'},
    'volatility': {label: 'Volatilite & RSI', icon: '📊'},
    'volume': {label: 'Hacim & Orderbook', icon: '📦'},
    'level': {label: 'Kırılım & Seviye', icon: '🎯'},
    'sentiment': {label: 'Duygu & Haber', icon: '🧠'}
  };
  var info = names[key] || {label: key, icon: '🤖'};
  var vAction = vote.action || 'HOLD';
  var vConf = Math.round((vote.confidence || 0) * 100);
  var acColor = vAction === 'BUY' ? '#34d399' : (vAction === 'SELL' ? '#fb7185' : '#94a3b8');
  var acText = vAction === 'BUY' ? 'AL' : (vAction === 'SELL' ? 'SAT' : 'BEKLE');

  var rows = [];
  if (key === 'trend') {
    rows = [['EMA 8', (scanData.ema8 || 0).toFixed(2)], ['EMA 21', (scanData.ema21 || 0).toFixed(2)],
            ['EMA Kesişim', scanData.ema_cross || 'yok'], ['MACD Hist', (scanData.macd_hist || 0).toFixed(2)],
            ['Fiyat Değ. (5bar)', (scanData.price_change_5 || 0).toFixed(2) + '%'], ['ATR %', (scanData.atr_pct || 0).toFixed(2) + '%']];
  } else if (key === 'volatility') {
    rows = [['RSI (14)', (scanData.rsi || 0).toFixed(1)], ['StochRSI', (scanData.stoch_rsi || 0).toFixed(1)],
            ['BB %B', (scanData.bb_pct || 0).toFixed(3)], ['ATR %', (scanData.atr_pct || 0).toFixed(2) + '%']];
  } else if (key === 'volume') {
    var ob = scanData.orderbook || {};
    rows = [['Hacim Oranı', (scanData.vol_ratio || 0).toFixed(2) + 'x'], ['Al/Sat Oranı', (ob.bid_ask_ratio || 0).toFixed(3)],
            ['OB Sinyal', ob.bid_ask_sinyal || 'notr'], ['Fiyat Değ.(5bar)', (scanData.price_change_5 || 0).toFixed(2) + '%']];
  } else if (key === 'level') {
    rows = [['Fiyat', '$' + (scanData.price || 0).toFixed(2)], ['Destek', '$' + (scanData.support || 0).toFixed(2)],
            ['Direnç', '$' + (scanData.resistance || 0).toFixed(2)], ['Yukarı Kırılım', scanData.breakout_up ? '🟢 EVET' : '❌ Hayır']];
  } else if (key === 'sentiment') {
    var fg = agent.fear_greed || 50;
    rows = [['Sentiment Skoru', (agent.last_sentiment || 0).toFixed(3)], ['Fear&Greed', fg.toFixed(0)]];
  }

  var h = '<div class="flex items-center justify-between mb-3">';
  h += '<div class="text-sm font-bold text-white">' + info.icon + ' ' + info.label + ' — <span style="color:' + acColor + '">' + acText + ' %' + vConf + '</span></div>';
  h += '<button onclick="closeAgentInline()" class="text-[10px] text-slate-400 hover:text-white">✕ KAPAT</button></div>';
  h += '<div style="background:rgba(255,255,255,0.02);border-radius:10px;border:1px solid rgba(255,255,255,0.05);overflow:hidden">';
  rows.forEach(function (r, i) {
    var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
    h += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03)">';
    h += '<span style="color:#94a3b8;font-size:11px">' + r[0] + '</span><span style="color:#e2e8f0;font-weight:700;font-size:11px;font-family:monospace">' + r[1] + '</span></div>';
  });
  h += '</div>';
  if (key === 'sentiment' && news.length > 0) {
    h += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:14px 0 8px">📰 İLGİLİ HABERLER</div>';
    h += '<div style="max-height:200px;overflow-y:auto">';
    news.forEach(function (n) {
      var u = n.url || '#';
      h += '<a href="' + u + '" target="_blank" rel="noopener" style="display:block;padding:8px 10px;border-radius:8px;margin-bottom:6px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);color:#cbd5e1;font-size:11px;line-height:1.4;text-decoration:none">' + (n.baslik || n.title || '') + '</a>';
    });
    h += '</div>';
  }
  return h;
}
function closeAgentInline() {
  var box = document.getElementById('agentDetailInline');
  if (box) box.style.display = 'none';
  _openAgentKey = null;
}

// ─── Haber akışı (tıklayınca açılır) ───
function updateNews() {
  fetch('/api/news').then(r => r.json()).then(list => {
    var box = document.getElementById('newsFeed');
    if (!box) return;
    if (!list || list.length === 0) {
      box.innerHTML = '<div class="text-slate-500 italic text-center py-4 text-xs">Henüz haber yok</div>';
      return;
    }
    var h = '';
    list.forEach(function (n) {
      var sent = n.sentiment || 'notr';
      var sIcon = sent === 'pozitif' ? '🟢' : (sent === 'negatif' ? '🔴' : '⚪');
      var sColor = sent === 'pozitif' ? '#34d399' : (sent === 'negatif' ? '#fb7185' : '#94a3b8');
      var u = n.url || '#';
      h += '<a href="' + u + '" target="_blank" rel="noopener" class="flex items-start gap-2 p-2.5 rounded-lg bg-surface-lowest/50 hover:bg-surface-lowest border border-white/5 transition-colors" style="text-decoration:none">';
      h += '<span class="text-sm mt-0.5">' + sIcon + '</span>';
      h += '<span class="flex-1 min-w-0"><span class="text-[11px] text-slate-200 leading-snug block">' + (n.baslik || n.title || 'Başlıksız') + '</span>';
      h += '<span class="text-[9px]" style="color:' + sColor + ';font-weight:700">' + sent.toUpperCase() + '</span></span>';
      h += '<span class="text-[10px] text-slate-500">↗</span></a>';
    });
    box.innerHTML = h;
  }).catch(() => {});
}

function startBot() {
  fetch('/api/start', {method: 'POST'}).then(r => r.json()).then(d => {
    showNotification('Algoritma başlatıldı!', 'success');
    setTimeout(updateStatus, 1200);
  }).catch(() => showNotification('Bağlantı hatası', 'error'));
}

function stopBot() {
  fetch('/api/stop', {method: 'POST'}).then(r => r.json()).then(d => {
    showNotification('Algoritma durduruldu.', 'warning');
    setTimeout(updateStatus, 1000);
  }).catch(() => showNotification('Bağlantı hatası', 'error'));
}

function resetAll() {
  if (!confirm('Tüm simülasyon sıfırlansın mı? (tüm işlemler, istatistikler, dersler ve bakiye)')) return;
  showNotification('Sıfırlanıyor...', 'info');
  fetch('/api/reset_all', {method: 'POST'}).then(r => r.json()).then(d => {
    showNotification(d.message || 'Sıfırlandı', d.success ? 'success' : 'error');
    setTimeout(function(){ updateStatus(); updatePnlHistory(); updateDecisions(); }, 1500);
  }).catch(() => showNotification('Bağlantı hatası', 'error'));
}

function toggleAiManage() {
  var box = document.getElementById('aiManageBox');
  var chev = document.getElementById('aiManageChevron');
  if (box.style.display === 'none') {
    box.style.display = 'block';
    chev.textContent = '▾';
    loadDirective();
  } else {
    box.style.display = 'none';
    chev.textContent = '▸';
  }
}

function loadDirective() {
  fetch('/api/directive').then(r => r.json()).then(d => {
    document.getElementById('directiveInput').value = d.directive || '';
  }).catch(() => {});
}

function trainDirective() {
  var txt = document.getElementById('directiveInput').value || '';
  fetch('/api/train_directive', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt: txt})
  }).then(r => r.json()).then(d => {
    document.getElementById('directiveStatus').textContent = d.success ? '✓ Kaydedildi' : ('✗ ' + d.message);
    showNotification(d.message || 'Kaydedildi', d.success ? 'success' : 'error');
  }).catch(() => showNotification('Bağlantı hatası', 'error'));
}

function updateReflection() {
  fetch('/api/reflection').then(r => r.json()).then(d => {
    var box = document.getElementById('reflectionBox');
    if (box && d.reflection) box.textContent = d.reflection;
    var db = document.getElementById('lastDebateBox');
    if (!db) return;
    var debate = d.debate;
    if (!debate || !debate.brains || debate.brains.length === 0) {
      db.innerHTML = '<div class="col-span-full text-[10px] text-slate-500 italic">Henüz tartışma yok</div>';
      return;
    }
    var h = '';
    debate.brains.forEach(function(b) {
      var v = b.karar || 'BEKLE';
      var col = v === 'AL' ? 'text-emerald-400' : (v === 'SAT' ? 'text-rose-400' : 'text-slate-400');
      var pct = Math.round((b.guven_skoru || 0) * 100);
      h += '<div class="rounded-lg border border-white/5 bg-surface-lowest/50 px-1.5 py-1 text-center">'
        + '<div class="text-[8px] font-bold text-slate-300 leading-tight">' + (b.ajan || b.name) + '</div>'
        + '<div class="text-[10px] font-extrabold ' + col + '">' + v + '</div>'
        + '<div class="text-[8px] font-mono ' + col + '">' + pct + '%</div>'
        + '</div>';
    });
    db.innerHTML = h;
  }).catch(() => {});
}

var _pnlData = [];
function updatePnlHistory() {
  fetch('/api/trade_pnl').then(r => r.json()).then(list => {
    var box = document.getElementById('pnlHistory');
    var totalEl = document.getElementById('pnlTotal');
    var countEl = document.getElementById('pnlCount');
    if (!box) return;
    var all = list || [];
    _pnlData = all;
    // Sadece gerceklesen (SAT/SELL) islemlerin K/Z'i anlamli; AL/BUY acilis oldugu icin pnl=0'dir.
    var realized = all.filter(function(t) { return t.action === 'SELL'; });
    if (all.length === 0) {
      box.innerHTML = '<div class="col-span-full text-slate-500 italic text-center py-6 text-xs">Henüz işlem yok</div>';
      if (totalEl) totalEl.textContent = '₺0,00';
      if (countEl) countEl.textContent = '0';
      return;
    }
    if (realized.length === 0) {
      box.innerHTML = '<div class="col-span-full text-slate-500 italic text-center py-6 text-xs">Henüz gerçekleşen (SAT) işlem yok</div>';
      if (totalEl) totalEl.textContent = '₺0,00';
      if (countEl) countEl.textContent = '0';
      return;
    }
    var total = 0;
    var html = '';
    realized.forEach(function(t, idx) {
      total += t.pnl;
      var pos = t.pnl >= 0;
      var cls = pos ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-rose-500/10 border-rose-500/30 text-rose-300';
      html += '<div onclick="openPnlDetail(' + idx + ')" class="rounded-lg border px-2 py-1.5 text-center ' + cls + ' cursor-pointer hover:scale-[1.04] hover:shadow-lg transition-all duration-200" title="Detay için tıkla">'
            + '<div class="text-[8px] opacity-70 font-bold">SAT</div>'
             + '<div class="text-xs font-extrabold font-mono">' + tryFmt(t.pnl) + '</div>'
            + '</div>';
    });
    box.innerHTML = html;
    if (totalEl) totalEl.textContent = tryFmt(total);
    if (countEl) countEl.textContent = String(realized.length);
  }).catch(() => {});
}

// ─── K/Z DETAY MODALI (aşağı açılmaz, overlay olarak gelir) ───
var _pnlTvWidget = null;
function openPnlDetail(idx) {
  var t = _pnlData.filter(function(x){return x.action === 'SELL';})[idx];
  if (!t) return;
  var modal = document.getElementById('pnlDetailModal');
  var title = document.getElementById('pnlModalTitle');
  var body = document.getElementById('pnlModalBody');

  var pos = t.pnl >= 0;
  var pnlColor = pos ? '#34d399' : '#fb7185';
  var pnlLabel = pos ? 'KÂR' : 'ZARAR';
  var tTime = (t.time || '').replace('T', ' ').substring(0, 19);
  var entry = t.entry_price || 0;
  var exit = t.price || 0;
  var roi = (entry > 0 && exit > 0) ? ((exit - entry) / entry * 100) : 0;
  var sym = pos ? '+' : '';

  var html = '';
  // Üst özet kart
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:14px;background:rgba(255,255,255,0.03);border-radius:12px;border:1px solid ' + (pos ? 'rgba(52,211,153,0.25)' : 'rgba(251,113,133,0.25)') + '">';
  html += '  <div>';
  html += '    <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px">NET K/Z</div>';
  html += '    <div style="font-size:22px;font-weight:900;color:' + pnlColor + ';font-family:monospace">' + sym + tryFmt(t.pnl) + '</div>';
  html += '  </div>';
  html += '  <div style="text-align:right">';
  html += '    <div style="font-size:10px;color:#64748b;font-weight:700">GETİRİ (ROI)</div>';
  html += '    <div style="font-size:18px;font-weight:900;color:' + (roi >= 0 ? '#34d399' : '#fb7185') + ';font-family:monospace">' + sym + roi.toFixed(2) + '%</div>';
  html += '  </div>';
  html += '</div>';

  // Teknik detay tablosu
  html += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">📋 İŞLEM BİLGİLERİ</div>';
  var rows = [
    ['Zaman', tTime || '--'],
    ['Mod', t.mode || 'SIM'],
    ['Giriş Fiyatı', entry > 0 ? '$' + entry.toFixed(2) : '--'],
    ['Çıkış Fiyatı', exit > 0 ? '$' + exit.toFixed(2) : '--'],
    ['Getiri %', (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%'],
    ['Net K/Z', (pos ? '+' : '') + tryFmt(t.pnl)]
  ];
  html += '<div style="background:rgba(255,255,255,0.02);border-radius:10px;border:1px solid rgba(255,255,255,0.05);overflow:hidden">';
  rows.forEach(function(r, i) {
    var bg = i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent';
    html += '<div style="display:flex;justify-content:space-between;padding:8px 12px;background:' + bg + ';border-bottom:1px solid rgba(255,255,255,0.03)">';
    html += '  <span style="color:#94a3b8;font-size:11px">' + r[0] + '</span>';
    html += '  <span style="color:#e2e8f0;font-weight:700;font-size:11px;font-family:monospace">' + r[1] + '</span>';
    html += '</div>';
  });
  html += '</div>';

  // Teknik Analiz Grafiği (canlı BTC/USD — TradingView)
  html += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:16px 0 8px">📈 TEKNİK ANALİZ GRAFİĞİ (BTC/USD)</div>';
  html += '<div id="pnlChartWrap" style="height:300px;width:100%;border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);background:#020617"></div>';

  // Equity eğrisi sparkline
  html += '<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:16px 0 6px">📊 EQUITY EĞRİSİ</div>';
  html += '<svg id="pnlEquitySpark" viewBox="0 0 200 50" preserveAspectRatio="none" style="width:100%;height:54px;background:rgba(255,255,255,0.02);border-radius:10px;border:1px solid rgba(255,255,255,0.05)"></svg>';

  body.innerHTML = html;
  modal.style.display = 'flex';
  setTimeout(function() { modal.classList.add('modal-visible'); }, 10);

  // TradingView mini grafik widget'ı
  setTimeout(function() {
    var el = document.getElementById('pnlChartWrap');
    if (!el) return;
    el.innerHTML = '';
    if (typeof TradingView === 'undefined') {
      el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#64748b;font-size:12px;text-align:center;padding:20px">Grafik yükleniyor...<br>(internet bağlantısı gerekli)</div>';
      setTimeout(openPnlDetailDrawChart, 1200);
      return;
    }
    openPnlDetailDrawChart();
  }, 60);

  // Equity sparkline
  fetch('/api/analytics').then(r => r.json()).then(d => {
    drawSpark(document.getElementById('pnlEquitySpark'), d.equity || []);
  }).catch(() => {});
}

function openPnlDetailDrawChart() {
  if (typeof TradingView === 'undefined') return;
  var el = document.getElementById('pnlChartWrap');
  if (!el) return;
  try {
    _pnlTvWidget = new TradingView.widget({
      "width": "100%",
      "height": "100%",
      "symbol": "COINBASE:BTCUSD",
      "interval": "15",
      "timezone": "Europe/Istanbul",
      "theme": "dark",
      "style": "1",
      "locale": "tr",
      "toolbar_bg": "#0e1424",
      "enable_publishing": false,
      "hide_side_toolbar": false,
      "allow_symbol_change": true,
      "autosize": true,
      "container_id": "pnlChartWrap"
    });
    // Widget'ın yeni (modal içi) boyuta uyum sağlaması için resize tetikle
    setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 80);
    setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 400);
  } catch (e) {
    el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#64748b;font-size:12px;text-align:center;padding:20px">Grafik yüklenemedi.</div>';
  }
}

function closePnlModal() {
  var modal = document.getElementById('pnlDetailModal');
  modal.classList.remove('modal-visible');
  setTimeout(function() {
    modal.style.display = 'none';
    if (_pnlTvWidget && _pnlTvWidget.remove) { try { _pnlTvWidget.remove(); } catch (e) {} }
    _pnlTvWidget = null;
  }, 200);
}

function manualBuy() {
  showNotification('Alım emri gönderiliyor...', 'info');
  fetch('/api/manual_buy', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({amount: 0})
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

    document.getElementById('sPortfolio').textContent = tryFmt(d.portfolio_value || 0);
    document.getElementById('sCash').textContent = tryFmt(d.cash || 0);
    document.getElementById('sScans').textContent = d.total_scans || 0;

    // START / STOP butonlarının aktif durumunu yansıt
    var btnStart = document.getElementById('btnStart');
    var btnStop = document.getElementById('btnStop');
    if (btnStart && btnStop) {
      if (d.running && !d.paused) {
        btnStart.className = 'btn text-[10px] font-bold px-2.5 py-1 rounded bg-emerald-600/30 text-emerald-300 border border-emerald-500/40';
        btnStop.className = 'btn text-[10px] font-bold px-2.5 py-1 rounded text-gray-400 hover:text-white';
      } else {
        btnStart.className = 'btn text-[10px] font-bold px-2.5 py-1 rounded text-gray-400 hover:text-white';
        btnStop.className = 'btn text-[10px] font-bold px-2.5 py-1 rounded ' + (d.paused ? 'bg-amber-600/30 text-amber-300 border border-amber-500/40' : 'text-gray-400 hover:text-white');
      }
    }

    var pl = d.kar_zarar || 0;
    var plEl = document.getElementById('sPnl');
    plEl.textContent = tryFmt(pl);
    plEl.className = 'text-xl font-mono font-bold ' + (pl >= 0 ? 'text-emerald-400' : 'text-rose-400');

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
        sh += '<td class="px-5 py-3 text-right font-semibold text-white">' + tryFmt(s.price) + '</td>';
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
        html += '    <span class="text-white font-semibold">' + tryFmt(t.price) + '</span>';
        var invested = (t.qty * (t.entry_price || t.price)) || 0;
        html += '    <span class="text-[10px] text-slate-400">Yat: ' + tryFmt(invested) + '</span>';
        html += '    <span class="text-[10px] text-slate-500 max-w-[90px] truncate">' + reasonStr + '</span>';
        html += '    <span class="px-2 py-0.5 rounded font-extrabold text-[10px] ' + pnlColor + '">' + (t.pnl !== 0 ? tryFmt(t.pnl) : '---') + '</span>';
        html += '  </div>';
        html += '</div>';
      });
      tradeList.innerHTML = html;
    } else {
      tradeList.innerHTML = '<div class="glass p-6 rounded-xl text-center text-slate-500 text-xs">Henüz işlem geçmişi yok.</div>';
    }
  }).catch(() => {});
}

function updateAnalytics() {
  fetch('/api/analytics').then(r => r.json()).then(d => {
    var s = d.stats || {};
    setText('aExpectancy', tryFmt(s.expectancy != null ? s.expectancy : 0));
    setText('aProfitFactor', s.profit_factor != null ? s.profit_factor.toFixed(2) : '--');
    setText('aWinRate', s.win_rate != null ? (s.win_rate * 100).toFixed(0) + '%' : '--');
    setText('aMaxDD', s.max_drawdown != null ? (s.max_drawdown * 100).toFixed(1) + '%' : '--');
    var meta = (s.total || 0) + ' işlem | Toplam K/Z ' + tryFmt(s.total_pnl != null ? s.total_pnl : 0) +
               ' | Ort.K ' + tryFmt(s.avg_win != null ? s.avg_win : 0) +
               ' / Ort.Z ' + tryFmt(s.avg_loss != null ? s.avg_loss : 0);
    setText('aMeta', meta);
    drawSpark(document.getElementById('equitySpark'), d.equity || []);
  }).catch(() => {});
}

function drawSpark(svg, data) {
  if (!svg || !data || !data.length) return;
  var W = 200, H = 50, pad = 4;
  var min = Math.min.apply(null, data), max = Math.max.apply(null, data);
  var rng = (max - min) || 1;
  var pts = data.map(function (v, i) {
    var x = data.length > 1 ? (i / (data.length - 1)) * W : W / 2;
    var y = H - pad - ((v - min) / rng) * (H - 2 * pad);
    return x.toFixed(1) + ',' + y.toFixed(1);
  }).join(' ');
  var last = data[data.length - 1];
  var color = last >= data[0] ? '#34d399' : '#fb7185';
  svg.innerHTML = '<polyline fill="none" stroke="' + color + '" stroke-width="1.5" points="' + pts + '"/>';
}

function setText(id, v) { var e = document.getElementById(id); if (e) e.textContent = v; }

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
      var today = localToday();
      var todays = (d || []).filter(function(g) { return g.date === today; });
      var pnl = todays.reduce(function(s, g) { return s + g.pnl; }, 0);
      var target = pv * (st.daily_goal_pct && st.daily_goal_pct > 0 ? st.daily_goal_pct/100 : 0.01);
      var pct = pv > 0 ? (pnl / pv * 100) : 0;
      var el = document.getElementById('goalText');
      var badge = document.getElementById('goalBadge');
      var pnlTry = tryFmt(pnl);
      if (pnl > 0) pnlTry = '+' + pnlTry;
      el.textContent = pnlTry + ' / HDF:' + tryFmt(target) + ' (' + pct.toFixed(2) + '%)';
      badge.title = (st.daily_goal_pct && st.daily_goal_pct > 0)
        ? ('Günlük hedef: %' + st.daily_goal_pct + (st.aggressive_mode ? ' (aç gözlülük modu AÇIK)' : ' (disiplinli mod)'))
        : 'Günlük sabit hedef yok (sadece risk yönetimi)' + (st.aggressive_mode ? ' • aç gözlülük modu AÇIK' : '');
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

function updateSelfImprove() {
  fetch('/api/self_improve').then(r => r.json()).then(d => {
    var p = d.params || {};
    var aggEl = document.getElementById('siAgg');
    var confEl = document.getElementById('siConf');
    var lesEl = document.getElementById('siLessons');
    if (!aggEl) return;
    aggEl.textContent = (p.position_aggressiveness || 1).toFixed(2) + 'x';
    confEl.textContent = (p.min_confidence_threshold || 0.45).toFixed(2);
    var lessons = d.lessons || [];
    if (lessons.length > 0) {
      var h = '';
      lessons.forEach(function(l) {
        var txt = l.lesson || '';
        var raw = l.time || '';
        var t = raw.length >= 19 ? raw.substring(11, 19) : '';
        var d = raw.length >= 10 ? raw.substring(5, 10) : '';
        var stamp = (d && t) ? (d + ' ' + t) : (d || t);
        var border = l.source === 'trade' ? 'border-amber-500/40' : 'border-emerald-500/40';
        var timeColor = l.source === 'trade' ? 'text-amber-400' : 'text-emerald-400';
        h += '<div class="bg-surface-lowest/50 rounded p-1.5 text-slate-300 border-l-2 ' + border + '">' + (stamp ? '<span class="' + timeColor + '">' + stamp + '</span> ' : '') + txt + '</div>';
      });
      lesEl.innerHTML = h;
    } else {
      lesEl.innerHTML = '<div class="text-slate-500 italic text-center py-4">Henüz ders yok</div>';
    }
  }).catch(() => {});
}

function updateDailyPnl() {
  fetch('/api/daily_pnl').then(r => r.json()).then(d => {
    var dt = document.getElementById('dailyPnlTotal');
    if (!dt) return;
    var ch = document.getElementById('dailyPnlChart');
    if (!d || d.length === 0) {
      dt.textContent = 'İşlem yok';
      if (ch) ch.innerHTML = '<div class="text-slate-500 italic text-center py-4 text-xs">Henüz günlük veri yok</div>';
      return;
    }
    var active = d.filter(function(g) { return g.count > 0; });
    var total = 0, totalWin = 0, totalLoss = 0;
    active.forEach(function(g) {
      total += g.pnl;
      if (g.pnl > 0) totalWin += g.pnl;
      else totalLoss += g.pnl;
    });
    dt.textContent = active.length === 0 ? 'İşlem yok' : ('NET: ' + tryFmt(total) + ' | Win: ' + tryFmt(totalWin) + ' / Loss: ' + tryFmt(totalLoss));
    
    var max = Math.max(...d.map(g => Math.abs(g.pnl)), 0.01);
    var h = '<div class="flex items-end justify-between gap-2.5 h-[140px] px-2 min-w-[280px]">';
    
    d.forEach(function(g) {
      var pct = Math.abs(g.pnl) / max * 100;
      var color = g.pnl > 0 ? '#10b981' : g.pnl < 0 ? '#ef4444' : '#475569';
      var barH = g.pnl === 0 ? 3 : Math.max(pct, 6);
      
      h += '<div class="flex-1 flex flex-col items-center justify-end h-full group">';
      h += '  <span class="text-[9px] font-bold mb-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200" style="color:' + color + '">' + tryShort(g.pnl) + '</span>';
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

      h += '<div class="glass rounded-xl p-3 border ' + (vAction !== 'HOLD' ? (vAction === 'BUY' ? 'border-emerald-500/20' : 'border-rose-500/20') : 'border-white/5') + ' transition-all duration-300 hover:scale-[1.02] hover:border-purple-500/40 cursor-pointer" onclick="toggleAgentInline(`' + key + '`)">';
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
      h += '  <div class="text-center mt-1"><span class="text-[8px] text-slate-600">Açmak için tıkla ▾</span></div>';
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
createChart('5');
loadFx();
updateStatus();
updateGoal();
updateSelfImprove();
updateDecisions();
updateDailyPnl();
updateAgents();
updatePnlHistory();
updateReflection();
updateNews();

// Polling intervals
setInterval(updateStatus, 5000);
setInterval(updateDecisions, 5000);
setInterval(updateDailyPnl, 10000);
setInterval(updateGoal, 15000);
setInterval(updatePnlHistory, 8000);
setInterval(updateReflection, 15000);
setInterval(updateSelfImprove, 15000);
setInterval(updateAgents, 5000);
setInterval(updateAnalytics, 10000);
setInterval(updateNews, 30000);
setInterval(loadFx, 300000);

// ==========================================
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
  <div style="background:linear-gradient(135deg,#14161f 0%,#1a1b21 100%);border-radius:20px;border:1px solid #232634;max-width:640px;width:92%;max-height:88vh;overflow-y:auto;padding:24px;box-shadow:0 25px 50px rgba(0,0,0,0.6)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <h3 style="font-size:18px;font-weight:900;color:white;margin:0">🧠 AI Beyinlerini Düzenle</h3>
      <button onclick="closeBrainsModal()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#94a3b8;font-size:16px;width:32px;height:32px;cursor:pointer;display:flex;align-items:center;justify-content:center">✕</button>
    </div>
    <p style="font-size:11px;color:#64748b;margin-bottom:14px;line-height:1.4">Her analiz bölümü için AI'ın nasıl düşüneceğini yaz. Bu talimatlar Gemini 5-Beyin tartışmasında kullanılır. İstediğin bilgiyi sen yazabilirsin.</p>
    <div id="brainsModalBody"></div>
    <div style="display:flex;gap:10px;margin-top:18px">
      <button onclick="saveBrains()" style="flex:1;background:linear-gradient(135deg,#3ad6ff,#22b8e6);color:#06222b;font-weight:800;font-size:13px;padding:12px;border-radius:12px;border:none;cursor:pointer">💾 KAYDET</button>
      <button onclick="closeBrainsModal()" style="background:rgba(255,255,255,0.06);color:#94a3b8;font-weight:700;font-size:13px;padding:12px 18px;border-radius:12px;border:1px solid rgba(255,255,255,0.1);cursor:pointer">İPTAL</button>
    </div>
  </div>
</div>

<!-- AJAN DETAY MODALI -->
<div id="agentDetailModal" onclick="if(event.target===this)closeAgentModal()" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);z-index:9999;justify-content:center;align-items:center;opacity:0;transition:opacity 0.2s ease">
  <div style="background:linear-gradient(135deg,#14161f 0%,#1a1b21 100%);border-radius:20px;border:1px solid #232634;max-width:520px;width:90%;max-height:85vh;overflow-y:auto;padding:24px;box-shadow:0 25px 50px rgba(0,0,0,0.6)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 id="modalTitle" style="font-size:18px;font-weight:900;color:white;margin:0"></h3>
      <button onclick="closeAgentModal()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#94a3b8;font-size:16px;width:32px;height:32px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s" onmouseover="this.style.background='rgba(255,255,255,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'">✕</button>
    </div>
    <div id="modalBody"></div>
  </div>
</div>
<!-- K/Z DETAY MODALI -->
<div id="pnlDetailModal" onclick="if(event.target===this)closePnlModal()" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);z-index:9999;justify-content:center;align-items:center;opacity:0;transition:opacity 0.2s ease">
  <div style="background:linear-gradient(135deg,#14161f 0%,#1a1b21 100%);border-radius:20px;border:1px solid #232634;max-width:680px;width:94%;max-height:88vh;overflow-y:auto;padding:24px;box-shadow:0 25px 50px rgba(0,0,0,0.6)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 id="pnlModalTitle" style="font-size:18px;font-weight:900;color:white;margin:0"></h3>
      <button onclick="closePnlModal()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#94a3b8;font-size:16px;width:32px;height:32px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s" onmouseover="this.style.background='rgba(255,255,255,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.05)'">✕</button>
    </div>
    <div id="pnlModalBody"></div>
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


@app.route('/api/analytics')
def api_analytics():
    from src import analytics
    from src.trader import trader
    trades = db.get_trade_history(200)
    rate = trader.get_usd_try_rate() or 1.0
    base_usd = settings.sim_starting_capital_tl / rate
    stats = analytics.compute_stats(trades, base_usd)
    eq = analytics.equity_curve(trades, base_usd)
    return jsonify({"stats": stats, "equity": eq, "starting_capital": base_usd})


@app.route('/api/start', methods=['POST'])
def api_start():
    bot.start()
    return jsonify({"success": True, "message": "Baslatildi", "running": bot.running, "paused": bot.paused})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    bot.stop()
    return jsonify({"success": True, "running": bot.running, "paused": bot.paused})


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
        data = request.get_json(silent=True) or {}
        amount = float(data.get('amount', 0))
        if amount <= 0:
            amount = settings.position_size_usd
        result = executor.buy(amount_usd=amount)
        if result and result.get("error") == "PERMISSION":
            return jsonify({"success": False, "message": result.get("message", "Binance işlem yetkisi yok")})
        if result:
            invested = result.get("cost", amount)
            db.save_trade("BUY", result["price"], result["qty"], 0, "Manuel Islem", result["price"], result.get("mode", "SIM"))
            tg.send(f"🟢 <b>MANUEL ALIS GERCEKLESTIRILDI</b>\n\nFiyat: <code>${result['price']:,.2f}</code>\nMiktar: <code>{result['qty']:.6f} BTC</code>\nTutar: <code>${invested:,.2f}</code>\nMod: <b>{result.get('mode', 'SIM')}</b>")
            return jsonify({"success": True, "message": f"{invested:,.2f} USDT değerinde alım yapıldı ({result.get('mode', 'SIM')})"})
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
    return jsonify(db.get_decisions(20))


@app.route('/api/trade_pnl')
def api_trade_pnl():
    return jsonify(db.get_trade_pnl(100))


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


@app.route('/api/fx')
def api_fx():
    from src.trader import trader
    return jsonify({"usd_try": trader.get_usd_try_rate()})


@app.route('/api/news')
def api_news():
    from src.bot import bot
    news = bot.last_news if hasattr(bot, 'last_news') else []
    return jsonify(news)

@app.route('/api/gemini_debate')
def api_gemini_debate():
    """Gemini 5-Brain AI tartışma sonucunu döndür."""
    from src import llm_agent
    debate = llm_agent.get_last_debate()
    if debate:
        return jsonify(debate)
    return jsonify({})


@app.route('/api/reset_sim', methods=['POST'])
def api_reset_sim():
    from src.executor import executor
    result = executor.reset_sim()
    if result.get('success'):
        try:
            # Simülasyon istatistiklerini de sıfırla (kazanma/kaybetme sayacı)
            from src import quant_agent
            for k in ("toplam_islem", "kazanma", "kaybetme", "ardisik_kayip",
                      "son_islem_kar_zarar", "son_giris_fiyati", "son_sl", "son_tp"):
                if k in quant_agent.state:
                    quant_agent.state[k] = 0
            quant_agent._save_state()
        except Exception as e:
            print(f"[RESET] istatistik sifirlama hatasi: {e}")
        try:
            from src.database import db
            from src.trader import trader
            try:
                price = trader.get_price()
            except Exception:
                price = 0
            db.save_decision(
                strategy_action="RESET", strategy_score=0.0,
                strategy_reason="Simülasyon baştan sona sıfırlandı (sermaye+pozisyon+istatistik)",
                ai_prob=0.0, ai_veto=False, final_action="RESET",
                final_reason="Kullanıcı simülasyonu sıfırladı", price=price, executed=0,
            )
        except Exception as e:
            print(f"[RESET] kayit hatasi: {e}")
        return jsonify({"success": True, "message": result.get('message'),
                        "starting_capital": result.get('starting_capital'),
                        "switched_to_sim": result.get('switched_to_sim', False)})
    return jsonify({"success": False, "message": result.get('message', 'Sıfırlanamadı')})


@app.route('/api/self_improve')
def api_self_improve():
    from src import self_improve
    return jsonify({"params": self_improve.get_params(), "lessons": self_improve.get_lessons(8)})


@app.route('/api/reset_all', methods=['POST'])
def api_reset_all():
    try:
        bot.reset_everything()
        return jsonify({"success": True, "message": "Simülasyon baştan sona sıfırlandı"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/directive', methods=['GET'])
def api_get_directive():
    from src import ai_brains
    return jsonify({"directive": ai_brains.load_directive()})


@app.route('/api/reflection', methods=['GET'])
def api_reflection():
    from src import self_improve
    from src import llm_agent
    return jsonify({"reflection": self_improve.build_recent_reflection(5),
                    "debate": llm_agent.get_last_debate()})


@app.route('/api/train_directive', methods=['POST'])
def api_train_directive():
    from src import ai_brains
    data = request.get_json(silent=True) or {}
    text = (data.get('prompt') or data.get('directive') or '').strip()
    try:
        ai_brains.save_directive(text)
        return jsonify({"success": True, "message": "5 beyin eğitim talimatı kaydedildi"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


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
