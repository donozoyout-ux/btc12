import sys
sys.path.insert(0, '.')
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
import threading
import json
from datetime import datetime
from src.config import settings
from src.main import bot, start_bot, stop_bot, pause_bot, get_status

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crypto-bot-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Crypto Scanner Bot</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: #0a0a1a; color: #e0e0e0; }
        .header { background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f3460; }
        .header h1 { color: #00d4ff; font-size: 24px; }
        .status-badge { padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 14px; }
        .status-running { background: #00c853; color: #000; }
        .status-stopped { background: #ff1744; color: #fff; }
        .status-paused { background: #ffc107; color: #000; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .controls { display: flex; gap: 10px; margin: 20px 0; }
        .btn { padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold; transition: all 0.3s; }
        .btn:hover { transform: translateY(-2px); }
        .btn-start { background: #00c853; color: #000; }
        .btn-stop { background: #ff1744; color: #fff; }
        .btn-pause { background: #ffc107; color: #000; }
        .btn-refresh { background: #2196f3; color: #fff; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }
        .stat-card { background: #1a1a2e; border: 1px solid #0f3460; border-radius: 12px; padding: 20px; text-align: center; }
        .stat-card h3 { color: #00d4ff; font-size: 14px; margin-bottom: 8px; }
        .stat-card .value { font-size: 28px; font-weight: bold; color: #fff; }
        .section { background: #1a1a2e; border: 1px solid #0f3460; border-radius: 12px; margin: 20px 0; overflow: hidden; }
        .section-header { padding: 15px 20px; border-bottom: 1px solid #0f3460; display: flex; justify-content: space-between; align-items: center; }
        .section-header h2 { color: #00d4ff; font-size: 16px; }
        .section-body { padding: 15px 20px; max-height: 400px; overflow-y: auto; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px 15px; text-align: left; border-bottom: 1px solid #0f3460; }
        th { color: #00d4ff; font-size: 12px; text-transform: uppercase; }
        .action-buy { color: #00c853; font-weight: bold; }
        .action-sell { color: #ff1744; font-weight: bold; }
        .action-hold { color: #888; }
        .confidence { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .conf-high { background: #00c853; color: #000; }
        .conf-med { background: #ffc107; color: #000; }
        .conf-low { background: #ff5722; color: #fff; }
        .signal-card { background: #0f3460; border-radius: 8px; padding: 12px; margin: 8px 0; }
        .signal-card .coin { font-size: 18px; font-weight: bold; color: #fff; }
        .signal-card .details { color: #aaa; font-size: 13px; margin-top: 5px; }
        .no-data { color: #666; text-align: center; padding: 40px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .scanning { animation: pulse 1s infinite; color: #ffc107; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Crypto Scanner Bot</h1>
        <div>
            <span id="statusBadge" class="status-badge status-stopped">STOPPED</span>
        </div>
    </div>
    <div class="container">
        <div class="controls">
            <button class="btn btn-start" onclick="startBot()">START</button>
            <button class="btn btn-stop" onclick="stopBot()">STOP</button>
            <button class="btn btn-pause" onclick="pauseBot()">PAUSE/RESUME</button>
            <button class="btn btn-refresh" onclick="refreshData()">REFRESH</button>
        </div>

        <div class="stats">
            <div class="stat-card">
                <h3>Total Scans</h3>
                <div class="value" id="totalScans">0</div>
            </div>
            <div class="stat-card">
                <h3>Signals Sent</h3>
                <div class="value" id="signalsSent">0</div>
            </div>
            <div class="stat-card">
                <h3>Coins Tracking</h3>
                <div class="value" id="symbolsCount">0</div>
            </div>
            <div class="stat-card">
                <h3>Last Scan</h3>
                <div class="value" id="lastScan">--:--</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="section">
                <div class="section-header">
                    <h2>Live Scan Results</h2>
                </div>
                <div class="section-body">
                    <table>
                        <thead>
                            <tr><th>Coin</th><th>Action</th><th>Confidence</th><th>Price</th><th>RSI</th><th>Volume</th></tr>
                        </thead>
                        <tbody id="scanResults">
                            <tr><td colspan="6" class="no-data">No scan data yet</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="section">
                <div class="section-header">
                    <h2>Recent Signals</h2>
                </div>
                <div class="section-body" id="recentSignals">
                    <div class="no-data">No signals yet</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function startBot() {
            fetch('/api/start', {method: 'POST'}).then(r => r.json()).then(d => {
                if(d.success) updateStatus();
            });
        }
        function stopBot() {
            fetch('/api/stop', {method: 'POST'}).then(r => r.json()).then(d => {
                if(d.success) updateStatus();
            });
        }
        function pauseBot() {
            fetch('/api/pause', {method: 'POST'}).then(r => r.json()).then(d => {
                updateStatus();
            });
        }
        function refreshData() {
            updateStatus();
        }
        function updateStatus() {
            fetch('/api/status').then(r => r.json()).then(data => {
                const badge = document.getElementById('statusBadge');
                if(data.running && !data.paused) {
                    badge.className = 'status-badge status-running';
                    badge.textContent = 'RUNNING';
                } else if(data.paused) {
                    badge.className = 'status-badge status-paused';
                    badge.textContent = 'PAUSED';
                } else {
                    badge.className = 'status-badge status-stopped';
                    badge.textContent = 'STOPPED';
                }
                document.getElementById('totalScans').textContent = data.total_scans;
                document.getElementById('signalsSent').textContent = data.signals_sent;
                document.getElementById('symbolsCount').textContent = data.symbols_count;
                document.getElementById('lastScan').textContent = data.last_scan_time || '--:--';

                // Scan results
                const tbody = document.getElementById('scanResults');
                if(data.scan_results && data.scan_results.length > 0) {
                    let html = '';
                    const sorted = [...data.scan_results].sort((a,b) => {
                        if(a.action === 'BUY' && b.action !== 'BUY') return -1;
                        if(a.action === 'SELL' && b.action !== 'SELL') return -1;
                        return (b.confidence || 0) - (a.confidence || 0);
                    });
                    sorted.forEach(r => {
                        if(r.action === 'HOLD') return;
                        const actionClass = r.action === 'BUY' ? 'action-buy' : r.action === 'SELL' ? 'action-sell' : 'action-hold';
                        const confClass = (r.confidence||0) >= 0.7 ? 'conf-high' : (r.confidence||0) >= 0.5 ? 'conf-med' : 'conf-low';
                        html += `<tr>
                            <td><b>${r.symbol}</b></td>
                            <td class="${actionClass}">${r.action}</td>
                            <td><span class="confidence ${confClass}">${((r.confidence||0)*100).toFixed(0)}%</span></td>
                            <td>$${(r.price||0).toFixed(4)}</td>
                            <td>${(r.rsi||0).toFixed(1)}</td>
                            <td>${(r.volume_ratio||0).toFixed(1)}x</td>
                        </tr>`;
                    });
                    tbody.innerHTML = html;
                }

                // Recent signals
                const signalsDiv = document.getElementById('recentSignals');
                if(data.last_signals && Object.keys(data.last_signals).length > 0) {
                    let html = '';
                    for(const [coin, sig] of Object.entries(data.last_signals)) {
                        const color = sig.action === 'BUY' ? '#00c853' : '#ff1744';
                        html += `<div class="signal-card">
                            <div class="coin" style="color:${color}">${coin} - ${sig.action}</div>
                            <div class="details">$${(sig.price||0).toFixed(4)} | Confidence: ${((sig.confidence||0)*100).toFixed(0)}%</div>
                        </div>`;
                    }
                    signalsDiv.innerHTML = html;
                }
            });
        }
        updateStatus();
        setInterval(updateStatus, 5000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/status')
def api_status():
    return jsonify(get_status())


@app.route('/api/start', methods=['POST'])
def api_start():
    success = start_bot()
    return jsonify({"success": success})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    success = stop_bot()
    return jsonify({"success": success})


@app.route('/api/pause', methods=['POST'])
def api_pause():
    paused = pause_bot()
    return jsonify({"success": True, "paused": paused})


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print(f"[PANEL] Starting on http://0.0.0.0:{port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
