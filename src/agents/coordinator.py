from src.agents.technical import TechnicalAgent
from src.agents.sentiment import SentimentAgent
from src.agents.volume import VolumeAgent
from src.agents.trend import TrendAgent
from src.agents.pattern import PatternAgent
from src.agents.ml_agent import MLAgent


class AgentCoordinator:
    def __init__(self):
        self.agents = [
            ("technical", TechnicalAgent(), 0.18),
            ("sentiment", SentimentAgent(), 0.12),
            ("volume", VolumeAgent(), 0.12),
            ("trend", TrendAgent(), 0.18),
            ("pattern", PatternAgent(), 0.10),
            ("ai_ml", MLAgent(), 0.30),
        ]
        self.last_results = {}
        self.signal_history = []

    def analyze_all(self, df, symbol=None):
        results = {}
        buy_total = 0
        sell_total = 0
        buy_count = 0
        sell_count = 0
        neutral_count = 0
        total_weight = 0

        for key, agent, weight in self.agents:
            try:
                if key == "sentiment":
                    result = agent.analyze(df, symbol)
                else:
                    result = agent.analyze(df)

                result["weight"] = weight
                result["agent_name"] = agent.name
                result["icon"] = agent.icon
                results[key] = result

                confidence = result.get("confidence", 0)
                direction = result.get("direction", "NEUTRAL")

                if direction == "BUY":
                    buy_total += confidence * weight
                    buy_count += 1
                elif direction == "SELL":
                    sell_total += confidence * weight
                    sell_count += 1
                else:
                    neutral_count += 1

                total_weight += weight

            except Exception as e:
                results[key] = {
                    "direction": "NEUTRAL", "confidence": 0,
                    "reason": f"Hata: {str(e)[:50]}",
                    "weight": weight, "agent_name": key, "icon": "error"
                }

        if total_weight > 0:
            buy_avg = buy_total / total_weight if buy_count > 0 else 0
            sell_avg = sell_total / total_weight if sell_count > 0 else 0
        else:
            buy_avg = buy_avg = 0

        MIN_AGREEMENTS = 2

        if buy_count >= MIN_AGREEMENTS and buy_total > sell_total:
            final = "BUY"
            final_conf = min(buy_avg * 1.1, 1.0)
        elif sell_count >= MIN_AGREEMENTS and sell_total > buy_total:
            final = "SELL"
            final_conf = min(sell_avg * 1.1, 1.0)
        else:
            final = "NEUTRAL"
            final_conf = max(buy_total, sell_total)

        buy_agents = [r["agent_name"] for r in results.values() if r["direction"] == "BUY"]
        sell_agents = [r["agent_name"] for r in results.values() if r["direction"] == "SELL"]

        if final == "BUY":
            consensus = len(buy_agents)
        elif final == "SELL":
            consensus = len(sell_agents)
        else:
            consensus = max(buy_count, sell_count)

        all_reasons = []
        for r in results.values():
            if r["direction"] != "NEUTRAL" and r.get("reason"):
                all_reasons.append(f"[{r['agent_name']}] {r['reason']}")

        self.last_results = results

        return {
            "direction": final,
            "confidence": final_conf,
            "buy_score": buy_total,
            "sell_score": sell_total,
            "consensus": consensus,
            "agents": results,
            "reasons": all_reasons,
            "summary": self._make_summary(final, final_conf, consensus, results)
        }

    def _make_summary(self, direction, confidence, consensus, results):
        if direction == "BUY":
            emoji = "ALIS"
        elif direction == "SELL":
            emoji = "SATIS"
        else:
            emoji = "BEKLE"

        agent_statuses = []
        for key, agent, weight in self.agents:
            r = results.get(key, {})
            d = r.get("direction", "?")
            c = r.get("confidence", 0)
            if d == "BUY":
                agent_statuses.append(f"{agent.name}: ALIS ({c:.0%})")
            elif d == "SELL":
                agent_statuses.append(f"{agent.name}: SATIS ({c:.0%})")
            else:
                agent_statuses.append(f"{agent.name}: BEKLE")

        return {
            "direction": emoji,
            "confidence": confidence,
            "consensus": consensus,
            "agent_statuses": agent_statuses
        }

    def get_last_results(self):
        return self.last_results


coordinator = AgentCoordinator()
