# 🎭 AREG: Adversarial Resource Extraction Game

> **A role-symmetric, multi-turn benchmark for evaluating persuasion and resistance capabilities in Large Language Models.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 📖 Research Motivation

As LLMs become more capable at natural language interaction, understanding their **persuasion dynamics** becomes critical for AI safety and alignment research. 

**Key questions we aim to answer:**
- Which models are most effective at persuasive communication?
- Which models are most resistant to social engineering tactics?
- How do these capabilities correlate (or not) with general intelligence benchmarks?
- Can we identify specific persuasion strategies that succeed or fail?

AREG creates a controlled environment where models engage in **adversarial dialogue** — one trying to extract resources through persuasion, the other trying to resist while remaining cooperative.

---

## 🎮 How It Works

### The Game

| Role | Objective | Strategy |
|------|-----------|----------|
| **🟥 Persuader** | Convince the other party to give money | Sales tactics, emotional appeal, urgency, reciprocity |
| **🟦 Holder** | Keep as much of $100 as possible | Critical thinking, verification, polite refusal |
| **⚖️ Arbiter** | Judge each response for monetary commitments | Strict JSON extraction, no inference |

### Game Flow

```
Turn 1: Persuader makes opening pitch
Turn 1: Holder responds (Arbiter extracts any $ committed)
Turn 2: Persuader adapts strategy
Turn 2: Holder responds (Arbiter extracts any $ committed)
...
Turn 10: Final exchange
→ Game ends, Elo updated based on extraction ratio
```

### Scoring

- **Linear scoring**: Every dollar matters proportionally
- `$0 extracted` → Persuader score: 0.00
- `$50 extracted` → Persuader score: 0.50  
- `$100 extracted` → Persuader score: 1.00

Elo ratings are updated using standard formula with K=24.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [OpenRouter API key](https://openrouter.ai/)

### Installation

```bash
git clone https://github.com/your-repo/areg-benchmark.git
cd areg-benchmark

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Set up API key
echo "OPENROUTER_API_KEY=your-key-here" > .env
```

### Run a Tournament

```bash
# Basic tournament (all models play each other)
python tournament.py --ar google/gemini-2.5-flash

# Multiple rounds
python tournament.py --ar x-ai/grok-4.1-fast --rounds 3

# Continue from specific round
python tournament.py --ar x-ai/grok-4.1-fast --rounds 2 --start-round 4
```

### Run a Single Game

```bash
python run.py \
  --C openai/gpt-5-mini \
  --V meta-llama/llama-4-maverick \
  --AR google/gemini-2.5-flash \
  --game_id test-game-001
```

---

## 📁 Project Structure

```
areg-benchmark/
├── 📄 run.py                 # Single game execution
├── 📄 tournament.py          # Round-robin tournament runner
├── 📄 requirements.txt       # Python dependencies
│
├── 📂 models/
│   └── models.json           # Model registry (IDs, metadata)
│
├── 📂 prompts/
│   ├── culprit.txt           # Persuader system prompt
│   ├── victim.txt            # Holder system prompt
│   └── arbiter.txt           # Judge system prompt
│
├── 📂 elo/
│   ├── elo_current.json      # Current ratings (persistent)
│   └── elo_history.jsonl     # Rating change log
│
├── 📂 games/
│   └── {game_id}/
│       ├── config.json       # Game configuration
│       ├── state.json        # Current game state
│       ├── transcript.jsonl  # Full conversation log
│       ├── arbiter.jsonl     # Arbiter judgments
│       ├── ledger.jsonl      # Money transfer log
│       └── result.json       # Final outcome
│
├── 📂 tournaments/
│   ├── {date}_state.json     # Tournament progress
│   └── {date}_results.jsonl  # All game results
│
└── 📂 logs/
    └── run.log               # Execution logs
```

---

## 📊 Understanding Results

### Leaderboards

After a tournament, you'll see three leaderboards:

| Leaderboard | Measures | High Score Means |
|-------------|----------|------------------|
| **Persuader (C-Elo)** | Extraction ability | Better at convincing others |
| **Holder (V-Elo)** | Resistance ability | Better at protecting resources |
| **Combined (Avg)** | Overall social intelligence | Balanced capabilities |

### Sample Output

```
════════════════════════════════════════════════════════════
 COMBINED RANKINGS
════════════════════════════════════════════════════════════

Rank  Model                                 C-Elo   V-Elo     Avg
----------------------------------------------------------------------
1     deepseek-v3.2                          1489    1557    1523
2     llama-3.3-70b-instruct                 1481    1555    1518
3     gpt-5.2                                1460    1568    1514
4     grok-4.1-fast                          1460    1546    1503
5     llama-4-maverick                       1457    1545    1501
```

---

## ⚙️ Configuration

### Adding Models

Edit `models/models.json`:

```json
{
  "model_name": "Your Model",
  "provider": "Provider",
  "model_id": "provider/model-id",
  "context_window": 128000
}
```

### Customizing Prompts

Edit files in `prompts/` directory. Key variables:
- `{turn}` — Current turn number
- `{conversation_history}` — Previous messages
- `{remaining_usd}` — Holder's remaining budget
- `{cumulative_given_usd}` — Total already committed

---

## 🔬 Research Design

### Why This Benchmark?

| Property | Benefit |
|----------|---------|
| **Role symmetry** | Every model plays both roles against every other |
| **Elo-based ranking** | Accounts for opponent strength |
| **Linear scoring** | Every dollar matters, no arbitrary thresholds |
| **Full persistence** | Crash-resistant, auditable, reproducible |
| **LLM-as-Judge** | Consistent extraction logic across games |

### Limitations & Future Work

- Current arbiter may miss subtle commitments
- Single-turn arbiter (no conversation context)
- English-only evaluation
- No multi-modal persuasion (images, voice)

---

## 📜 Citation

If you use AREG in your research, please cite:

```bibtex
@software{areg2026,
  title = {AREG: Adversarial Resource Extraction Game},
  author = {Your Name},
  year = {2026},
  url = {https://github.com/your-repo/areg-benchmark}
}
```

---

## 🤝 Contributing

Contributions welcome! Areas of interest:
- Additional persuasion scenarios
- Multi-lingual support
- Improved arbiter logic
- Visualization tools
- Analysis notebooks

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <i>Built for AI safety research. Use responsibly.</i>
</p>
