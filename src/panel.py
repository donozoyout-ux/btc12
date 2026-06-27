import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify, request
import threading
import time
from datetime import datetime
from src.config import settings
from src.main import CryptoBot

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crypto-bot-secret'

bot = None
bot_thread = None
log_messages = []


def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    entry = f"[{timestamp}] {msg}"
    log_messages.append(entry)
    if len(log_messages) > 100:
        log_messages.pop(0)
    print(entry)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Scanner Bot</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: #0a0a1a; color: #e0e0e0; min-height: 100vh; }
        .header { background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f3460; }
        .header h1 { color: #00d4ff; font-size: 22px; }
        .status-box { display: flex; align-items: center; gap: 10px; }
        .status-dot { width: 12px; height: 12px; border-radius: 50%; }
        .dot-running { background: #00c853; box-shadow: 0 0 10px #00c853; animation: pulse 1s infinite; }
        .dot-stopped { background: #ff1744; }
        .dot-paused { background: #ffc107; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .controls { display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
        .btn { padding: 14px 28px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold; transition: all 0.3s; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        .btn:active { transform: translateY(0); }
        .btn-start { background: #00c853; color: #000; }
        .btn-stop { background: #ff1744; color: #fff; }
        .btn-pause { background: #ffc107; color: #000; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #1a1a2e; border: 1px solid #0f3460; border-radius: 12px; padding: 15px; text-align: center; }
        .stat-card h3 { color: #00d4ff; font-size: 12px; margin-bottom: 5px; text-transform: uppercase; }
        .stat-card .value { font-size: 24px; font-weight: bold; color: #fff; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
        .section { background: #1a1a2e; border: 1px solid #0f3460; border-radius: 12px; overflow: hidden; }
        .section-header { padding: 12px 15px; border-bottom: 1px solid #0f3460; background: #16213e; }
        .section-header h2 { color: #00d4ff; font-size: 14px; }
        .section-body { padding: 10px; max-height: 350px; overflow-y: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #0f3460; }
        th { color: #00d4ff; font-size: 11px; text-transform: uppercase; }
        .buy { color: #00c853; font-weight: bold; }
        .sell { color: #ff1744; font-weight: bold; }
        .hold { color: #555; }
        .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .badge-high { background: #00c853; color: #000; }
        .badge-med { background: #ffc107; color: #000; }
        .badge-low { background: #ff5722; color: #fff; }
        .log-box { background: #0d1117; border-radius: 8px; padding: 10px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; color: #8b949e; }
        .log-entry { padding: 2px 0; }
        .signal-item { background: #0f3460; border-radius: 6px; padding: 10px; margin: 5px 0; }
        .signal-coin { font-weight: bold; font-size: 16px; }
        .no-data { color: #555; text-align: center; padding: 30px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #000; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 5px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        #toast { position: fixed; top: 20px; right: 20px; padding: 15px 25px; border-radius: 8px; font-weight: bold; z-index: 999; transition: all 0.3s; opacity: 0; transform: translateX(100px); }
        #toast.show { opacity: 1; transform: translateX(0); }
        #toast.success { background: #00c853; color: #000; }
        #toast.error { background: #ff1744; color: #fff; }
        #toast.info { background: #2196f3; color: #fff; }
    </style>
</head>
<body>
    <div id="toast"></div>
    <div class="header">
        <h1>Crypto Scanner Bot</h1>
        <div class="status-box">
            <div id="statusDot" class="status-dot dot-stopped"></div>
            <span id="statusText" style="font-weight:bold;">STOPPED</span>
        </div>
    </div>
    <div class="container">
        <div class="controls">
            <button id="btnStart" class="btn btn-start" onclick="startBot()">START</button>
            <button id="btnStop" class="btn btn-stop" onclick="stopBot()">STOP</button>
            <button id="btnPause" class="btn btn-pause" onclick="pauseBot()">PAUSE</button>
        </div>

        <div class="stats">
            <div class="stat-card"><h3>Status</h3><div class="value" id="statStatus">-</div></div>
            <div class="stat-card"><h3>Scans</h3><div class="value" id="statScans">0</div></div>
            <div class="stat-card"><h3>Signals</h3><div class="value" id="statSignals">0</div></div>
            <div class="stat-card"><h3>Coins</h3><div class="value" id="statCoins">0</div></div>
            <div class="stat-card"><h3>Last Scan</h3><div class="value" id="statLastScan">--:--</div></div>
        </div>

        <div class="grid">
            <div class="section">
                <div class="section-header"><h2>BUY / SELL Signals</h2></div>
                <div class="section-body" id="signalsBody">
                    <div class="no-data">No signals yet</div>
                </div>
            </div>
            <div class="section">
                <div class="section-header"><h2>All Scan Results</h2></div>
                <div class="section-body" style="max-height:300px;">
                    <table>
                        <thead><tr><th>Coin</th><th>Action</th><th>Conf</th><th>Price</th><th>RSI</th></tr></thead>
                        <tbody id="scanBody"><tr><td colspan="5" class="no-data">Waiting for scan...</td></tr></tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="section" style="margin-top:15px;">
            <div class="section-header"><h2>Logs</h2></div>
            <div class="section-body">
                <div class="log-box" id="logBox"></div>
            </div>
        </div>
    </div>

    <script>
        function toast(msg, type) {
            var t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'show ' + type;
            setTimeout(function(){ t.className = ''; }, 3000);
        }

        function startBot() {
            document.getElementById('btnStart').disabled = true;
            document.getElementById('btnStart').innerHTML = '<span class="spinner"></span>Starting...';
            fetch('/api/start', {method: 'POST'})
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    if(d.success) {
                        toast('Bot started!', 'success');
                        setTimeout(updateStatus, 2000);
                    } else {
                        toast(d.message || 'Failed to start', 'error');
                    }
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStart').innerHTML = 'START';
                })
                .catch(function(e) {
                    toast('Error: ' + e, 'error');
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStart').innerHTML = 'START';
                });
        }

        function stopBot() {
            fetch('/api/stop', {method: 'POST'})
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    toast('Bot stopped', 'info');
                    setTimeout(updateStatus, 1000);
                });
        }

        function pauseBot() {
            fetch('/api/pause', {method: 'POST'})
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    toast(d.paused ? 'Paused' : 'Resumed', 'info');
                    setTimeout(updateStatus, 1000);
                });
        }

        function updateStatus() {
            fetch('/api/status')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var dot = document.getElementById('statusDot');
                    var txt = document.getElementById('statusText');

                    if(d.running && !d.paused) {
                        dot.className = 'status-dot dot-running';
                        txt.textContent = 'RUNNING';
                        txt.style.color = '#00c853';
                        document.getElementById('statStatus').textContent = 'RUNNING';
                        document.getElementById('statStatus').style.color = '#00c853';
                    } else if(d.paused) {
                        dot.className = 'status-dot dot-paused';
                        txt.textContent = 'PAUSED';
                        txt.style.color = '#ffc107';
                        document.getElementById('statStatus').textContent = 'PAUSED';
                        document.getElementById('statStatus').style.color = '#ffc107';
                    } else {
                        dot.className = 'status-dot dot-stopped';
                        txt.textContent = 'STOPPED';
                        txt.style.color = '#ff1744';
                        document.getElementById('statStatus').textContent = 'STOPPED';
                        document.getElementById('statStatus').style.color = '#ff1744';
                    }

                    document.getElementById('statScans').textContent = d.total_scans;
                    document.getElementById('statSignals').textContent = d.signals_sent;
                    document.getElementById('statCoins').textContent = d.symbols_count;
                    document.getElementById('statLastScan').textContent = d.last_scan_time || '--:--';

                    var signalsHtml = '';
                    if(d.last_signals && Object.keys(d.last_signals).length > 0) {
                        for(var coin in d.last_signals) {
                            var sig = d.last_signals[coin];
                            var color = sig.action === 'BUY' ? '#00c853' : '#ff1744';
                            signalsHtml += '<div class="signal-item">' +
                                '<div class="signal-coin" style="color:' + color + '">' + coin + ' - ' + sig.action + '</div>' +
                                '<div style="color:#888;font-size:12px;">$' + (sig.price||0).toFixed(4) + ' | ' + ((sig.confidence||0)*100).toFixed(0) + '%</div>' +
                                '</div>';
                        }
                    } else {
                        signalsHtml = '<div class="no-data">No signals yet</div>';
                    }
                    document.getElementById('signalsBody').innerHTML = signalsHtml;

                    // Scan results table
                    var scanBody = document.getElementById('scanBody');
                    if(d.scan_results && d.scan_results.length > 0) {
                        var sorted = d.scan_results.filter(function(r){ return r.action !== 'HOLD'; });
                        sorted.sort(function(a,b){ return (b.confidence||0) - (a.confidence||0); });
                        if(sorted.length === 0) sorted = d.scan_results;
                        var rows = '';
                        sorted.forEach(function(r) {
                            var cls = r.action === 'BUY' ? 'buy' : r.action === 'SELL' ? 'sell' : 'hold';
                            rows += '<tr><td><b>' + r.symbol + '</b></td>' +
                                '<td class="' + cls + '">' + r.action + '</td>' +
                                '<td>' + ((r.confidence||0)*100).toFixed(0) + '%</td>' +
                                '<td>$' + (r.price||0).toFixed(4) + '</td>' +
                                '<td>' + (r.rsi||0).toFixed(1) + '</td></tr>';
                        });
                        scanBody.innerHTML = rows;
                    }

                    if(d.logs && d.logs.length > 0) {
                        var logHtml = '';
                        d.logs.reverse().forEach(function(l) {
                            logHtml += '<div class="log-entry">' + l + '</div>';
                        });
                        document.getElementById('logBox').innerHTML = logHtml;
                    }
                })
                .catch(function(e) {
                    console.log('Status error:', e);
                });
        }

        updateStatus();
        setInterval(updateStatus, 3000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/status')
def api_status():
    global bot
    status = {
        "running": bot.running if bot else False,
        "paused": bot.paused if bot else False,
        "total_scans": bot.total_scans if bot else 0,
        "signals_sent": bot.signals_sent if bot else 0,
        "last_scan_time": bot.last_scan_time if bot else None,
        "symbols_count": len(settings.symbols),
        "scan_results": bot.scan_results if bot else [],
        "last_signals": {},
        "logs": log_messages[-30:]
    }
    if bot and bot.last_signals:
        for k, v in bot.last_signals.items():
            status["last_signals"][k] = {
                "action": v.action,
                "confidence": v.confidence,
                "price": v.price
            }
    return jsonify(status)


@app.route('/api/start', methods=['POST'])
def api_start():
    global bot, bot_thread
    try:
        if bot and bot.running:
            return jsonify({"success": False, "message": "Bot already running"})

        log("Starting bot...")
        bot = CryptoBot()

        if not bot.check_connection():
            log("Failed to connect to Alpaca API")
            return jsonify({"success": False, "message": "Failed to connect to Alpaca API. Check your API keys."})

        bot_thread = threading.Thread(target=bot.run, daemon=True)
        bot_thread.start()

        time.sleep(2)
        if bot.running:
            log("Bot started successfully!")
            return jsonify({"success": True, "message": "Bot started"})
        else:
            log("Bot failed to start")
            return jsonify({"success": False, "message": "Failed to start bot"})
    except Exception as e:
        log(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    global bot
    try:
        if bot:
            bot.running = False
            log("Bot stopped")
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "No bot running"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/pause', methods=['POST'])
def api_pause():
    global bot
    try:
        if bot:
            bot.paused = not bot.paused
            state = "paused" if bot.paused else "resumed"
            log(f"Bot {state}")
            return jsonify({"success": True, "paused": bot.paused})
        return jsonify({"success": False})
    except Exception as e:
        return jsonify({"success": False})


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    log("Panel started")
    log(f"Tracking {len(settings.symbols)} coins")
    print(f"[PANEL] http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
