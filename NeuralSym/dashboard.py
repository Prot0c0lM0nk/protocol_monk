import json
from pathlib import Path
from collections import Counter

class DashboardGenerator:
    def __init__(self, analyzer, knowledge_graph, guidance_system):
        self.analyzer = analyzer
        self.kg = knowledge_graph
        self.guidance = guidance_system

    def generate(self, output_path: str = "agent_brain.html"):
        stats = self._gather_stats()
        html = self._build_html(stats)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return Path(output_path).absolute()

    def _gather_stats(self):
        # Gather interactions
        interactions = list(self.analyzer.interactions.values())
        
        # 1. Pattern Metrics
        outcomes = Counter([i.outcome.value for i in interactions])
        
        # 2. Knowledge Metrics (Failures)
        failures = [
            {"tool": f.value.get("tool"), "reason": f.value.get("reason"), "time": f.updated_at}
            for f in self.kg.get_facts_by_type("tool_rejection")
            if f.status.name == "REFUTED" and isinstance(f.value, dict)
        ]
        failures.sort(key=lambda x: x['time'], reverse=True)

        # 3. Guidance Decisions (The new part)
        decisions = self.guidance.decision_log[-10:] # Get last 10 decisions
        # Reverse to show newest first
        decisions = decisions[::-1]

        return {
            "total_interactions": len(interactions),
            "success_rate": round((outcomes.get("success", 0) / (len(interactions) or 1)) * 100, 1),
            "outcomes": dict(outcomes),
            "recent_failures": failures[:10],
            "decisions": decisions
        }

    def _build_html(self, stats: dict) -> str:
        stats_json = json.dumps(stats)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agent Neural Diagnostic</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                :root {{ --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --accent: #38bdf8; --danger: #ef4444; --success: #22c55e; }}
                body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); padding: 20px; margin: 0; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                
                /* Header */
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 1px solid #334155; padding-bottom: 20px; }}
                h1 {{ margin: 0; font-size: 24px; }}
                .badge {{ background: var(--accent); color: var(--bg); padding: 5px 10px; border-radius: 12px; font-weight: bold; }}

                /* Grid Layout */
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }}
                .card {{ background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
                h2 {{ margin-top: 0; font-size: 18px; color: #94a3b8; }}

                /* Decision Stream Styling */
                .decision-stream {{ display: flex; flex-direction: column; gap: 15px; }}
                .decision-node {{ background: #0f172a; border-left: 4px solid var(--accent); padding: 15px; border-radius: 4px; }}
                .decision-meta {{ display: flex; justify-content: space-between; font-size: 0.8em; color: #64748b; margin-bottom: 10px; }}
                .logic-trace {{ font-family: monospace; font-size: 0.9em; color: #fbbf24; margin: 5px 0; }}
                .prompt-preview {{ background: #1e293b; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 0.85em; white-space: pre-wrap; border: 1px solid #334155; color: #a5b4fc; }}
                
                /* Tables */
                table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
                th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #334155; }}
                th {{ color: #94a3b8; }}
                .tag-danger {{ color: var(--danger); font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div>
                        <h1>🧠 Neural Diagnostic Dashboard</h1>
                        <div style="color: #64748b; font-size: 0.9em">Guidance System & Pattern Analysis</div>
                    </div>
                    <div class="badge">Success Rate: {stats['success_rate']}%</div>
                </div>
                
                <div class="grid">
                    <div class="card">
                        <h2>Outcome Distribution</h2>
                        <div style="height: 200px"><canvas id="outcomeChart"></canvas></div>
                    </div>
                    <div class="card">
                        <h2>Active Constraints (Failures)</h2>
                        <table>
                            <thead><tr><th>Tool</th><th>Reason</th></tr></thead>
                            <tbody id="failureTable"></tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h2>🔍 Guidance Decision Trace (Last 10 Prompts)</h2>
                    <p style="font-size: 0.9em; color: #64748b;">This stream shows exactly how the system decided to instruct the LLM.</p>
                    <div id="decisionStream" class="decision-stream"></div>
                </div>
            </div>

            <script>
                const data = {stats_json};

                // 1. Render Outcomes Chart
                new Chart(document.getElementById('outcomeChart'), {{
                    type: 'doughnut',
                    data: {{
                        labels: Object.keys(data.outcomes),
                        datasets: [{{
                            data: Object.values(data.outcomes),
                            backgroundColor: ['#22c55e', '#ef4444', '#fbbf24'],
                            borderWidth: 0
                        }}]
                    }},
                    options: {{ maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right', labels: {{ color: '#94a3b8' }} }} }} }}
                }});

                // 2. Render Failures Table
                const failTable = document.getElementById('failureTable');
                data.recent_failures.forEach(f => {{
                    const row = `<tr><td style="font-weight:bold">${{f.tool}}</td><td class="tag-danger">${{f.reason.substring(0, 50)}}...</td></tr>`;
                    failTable.innerHTML += row;
                }});

                // 3. Render Decision Stream
                const streamDiv = document.getElementById('decisionStream');
                data.decisions.forEach(d => {{
                    // Format inputs for display
                    const risks = d.inputs.risks && d.inputs.risks.length > 0 ? 
                        `<span style="color:var(--danger)">⚠️ ${{d.inputs.risks.length}} Risks Detected</span>` : 
                        `<span style="color:var(--success)">✓ No Risks</span>`;
                    
                    const logic = d.logic_path.join(" → ");
                    
                    const html = `
                        <div class="decision-node">
                            <div class="decision-meta">
                                <strong>INTENT: ${{d.intent}}</strong>
                                <span>${{risks}}</span>
                            </div>
                            <div class="logic-trace">Logic Path: ${{logic}}</div>
                            <div class="prompt-preview">${{d.final_output}}</div>
                        </div>
                    `;
                    streamDiv.innerHTML += html;
                }});
            </script>
        </body>
        </html>
        """