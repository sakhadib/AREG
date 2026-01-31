"""
AREG Dataset Generator
======================
Transforms raw game data into relational CSV format for research publication.

Output Structure (dataset/):
├── models.csv           - Model registry with metadata
├── games.csv            - Game-level summary (one row per game)
├── turns.csv            - Turn-level data (one row per turn, both roles)
├── messages.csv         - Full conversation messages
├── arbiter_verdicts.csv - Arbiter judgments per victim turn
├── transfers.csv        - Money transfer events (ledger)
├── elo_history.csv      - Elo rating changes over time
├── elo_final.csv        - Final Elo ratings snapshot

Relational Keys:
- models.csv: model_id (PK)
- games.csv: game_id (PK), culprit_model_id (FK), victim_model_id (FK), arbiter_model_id (FK)
- turns.csv: game_id (FK), turn_number, role
- messages.csv: game_id (FK), turn_number, role
- arbiter_verdicts.csv: game_id (FK), victim_turn
- transfers.csv: game_id (FK), turn
- elo_history.csv: game_id (FK), model_id (FK)
"""

import os
import json
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = Path(__file__).parent
GAMES_DIR = BASE_DIR / "games"
MODELS_FILE = BASE_DIR / "models" / "models.json"
ELO_CURRENT_FILE = BASE_DIR / "elo" / "elo_current.json"
ELO_HISTORY_FILE = BASE_DIR / "elo" / "elo_history.jsonl"
TOURNAMENTS_DIR = BASE_DIR / "tournaments"
OUTPUT_DIR = BASE_DIR / "dataset"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_json(path: Path) -> dict | list | None:
    """Load JSON file, return None if not found."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file, return empty list if not found."""
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def sanitize_text(value) -> str:
    """Replace newlines and problematic characters for CSV safety."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    # Replace newlines with literal \n for CSV compatibility
    # Replace carriage returns as well
    return value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict], text_fields: list[str] = None):
    """Write list of dicts to CSV with proper text sanitization."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Sanitize text fields that may contain newlines
    if text_fields:
        sanitized_rows = []
        for row in rows:
            new_row = dict(row)
            for field in text_fields:
                if field in new_row:
                    new_row[field] = sanitize_text(new_row[field])
            sanitized_rows.append(new_row)
        rows = sanitized_rows
    
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✓ {path.name}: {len(rows)} rows")


def extract_round_from_game_id(game_id: str) -> int:
    """Extract tournament round number from game_id."""
    # Format: 2026-01-31_R2_model1_vs_model2 or 2026-01-30_model1_vs_model2
    parts = game_id.split("_")
    for part in parts:
        if part.startswith("R") and part[1:].isdigit():
            return int(part[1:])
    return 1  # Default to round 1 if no R prefix


def extract_date_from_game_id(game_id: str) -> str:
    """Extract date from game_id."""
    # Format: 2026-01-31_...
    return game_id.split("_")[0]


def model_id_to_short_name(model_id: str) -> str:
    """Convert full model_id to short name."""
    # openai/gpt-5.2 -> gpt-5.2
    return model_id.split("/")[-1] if "/" in model_id else model_id


# ============================================================================
# DATA EXTRACTION
# ============================================================================

def build_models_table() -> list[dict]:
    """Build models.csv from models.json."""
    models_data = load_json(MODELS_FILE) or []
    rows = []
    
    for m in models_data:
        rows.append({
            "model_id": m.get("model_id", ""),
            "model_name": m.get("model_name", ""),
            "provider": m.get("provider", ""),
            "short_name": model_id_to_short_name(m.get("model_id", "")),
            "context_window": m.get("context_window", ""),
            "parameters": m.get("parameters", ""),
            "release_date": m.get("release_date", ""),
            "knowledge_cutoff": m.get("knowledge_cutoff", ""),
            "input_price_per_1m": m.get("input_price_per_1m_tokens", ""),
            "output_price_per_1m": m.get("output_price_per_1m_tokens", ""),
            "architecture": m.get("architecture", ""),
            "modalities": m.get("modalities", ""),
            "use_case": m.get("use_case", ""),
            "special_features": m.get("special_features", ""),
            # Flatten some benchmarks
            "benchmark_mmlu": m.get("benchmarks", {}).get("MMLU_CoT", ""),
            "benchmark_gpqa": m.get("benchmarks", {}).get("GPQA", ""),
            "benchmark_humaneval": m.get("benchmarks", {}).get("HumanEval", ""),
            "benchmark_gsm8k": m.get("benchmarks", {}).get("GSM8K", ""),
            "benchmark_math": m.get("benchmarks", {}).get("MATH", ""),
        })
    
    return rows


def build_games_table() -> list[dict]:
    """Build games.csv from all game result files."""
    rows = []
    
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        
        config = load_json(game_dir / "config.json")
        result = load_json(game_dir / "result.json")
        state = load_json(game_dir / "state.json")
        
        if not config:
            continue
        
        game_id = config.get("game_id", game_dir.name)
        
        # Count messages for conversation length stats
        transcript = load_jsonl(game_dir / "transcript.jsonl")
        total_chars = sum(len(t.get("message", "")) for t in transcript)
        culprit_chars = sum(len(t.get("message", "")) for t in transcript if t.get("role") == "culprit")
        victim_chars = sum(len(t.get("message", "")) for t in transcript if t.get("role") == "victim")
        
        # Count arbiter verdicts with money
        arbiter_verdicts = load_jsonl(game_dir / "arbiter.jsonl")
        turns_with_extraction = sum(1 for v in arbiter_verdicts if v.get("given_usd", 0) > 0)
        
        row = {
            "game_id": game_id,
            "date": extract_date_from_game_id(game_id),
            "round": extract_round_from_game_id(game_id),
            "culprit_model_id": config.get("culprit_model", ""),
            "victim_model_id": config.get("victim_model", ""),
            "arbiter_model_id": config.get("arbiter_model", ""),
            "culprit_short": model_id_to_short_name(config.get("culprit_model", "")),
            "victim_short": model_id_to_short_name(config.get("victim_model", "")),
            "arbiter_short": model_id_to_short_name(config.get("arbiter_model", "")),
            "initial_usd": config.get("initial_usd", 100),
            "max_turns": config.get("max_turns", 10),
            "started_at": config.get("started_at", ""),
            "completed_at": result.get("completed_at", "") if result else "",
            "total_turns": result.get("total_turns", state.get("current_turn", 0) if state else 0) if result else (state.get("current_turn", 0) if state else 0),
            "extracted_usd": result.get("extracted_usd", 0) if result else 0,
            "remaining_usd": state.get("remaining_usd", 100) if state else 100,
            "extraction_ratio": result.get("extraction_ratio", 0) if result else 0,
            "outcome": result.get("outcome", "incomplete") if result else "incomplete",
            "is_complete": 1 if result else 0,
            "total_message_chars": total_chars,
            "culprit_chars": culprit_chars,
            "victim_chars": victim_chars,
            "turns_with_extraction": turns_with_extraction,
        }
        rows.append(row)
    
    return rows


def build_messages_table() -> list[dict]:
    """Build messages.csv from all transcript files."""
    rows = []
    
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        
        game_id = game_dir.name
        transcript = load_jsonl(game_dir / "transcript.jsonl")
        
        for i, entry in enumerate(transcript):
            rows.append({
                "game_id": game_id,
                "message_index": i,
                "turn": entry.get("turn", 0),
                "role": entry.get("role", ""),
                "model_id": entry.get("model", ""),
                "model_short": model_id_to_short_name(entry.get("model", "")),
                "message": entry.get("message", ""),
                "message_length": len(entry.get("message", "")),
                "timestamp": entry.get("timestamp", ""),
            })
    
    return rows


def build_turns_table() -> list[dict]:
    """Build turns.csv - aggregated turn-level data."""
    rows = []
    
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        
        game_id = game_dir.name
        config = load_json(game_dir / "config.json")
        transcript = load_jsonl(game_dir / "transcript.jsonl")
        arbiter_verdicts = load_jsonl(game_dir / "arbiter.jsonl")
        
        # Build verdict lookup by victim turn
        verdict_by_turn = {v.get("victim_turn"): v for v in arbiter_verdicts}
        
        # Group messages by turn
        turns_data = defaultdict(dict)
        for entry in transcript:
            turn = entry.get("turn", 0)
            role = entry.get("role", "")
            turns_data[turn][role] = entry
        
        # Build turn rows
        for turn_num in sorted(turns_data.keys()):
            turn_messages = turns_data[turn_num]
            verdict = verdict_by_turn.get(turn_num, {})
            
            culprit_msg = turn_messages.get("culprit", {})
            victim_msg = turn_messages.get("victim", {})
            
            rows.append({
                "game_id": game_id,
                "turn": turn_num,
                "culprit_model_id": culprit_msg.get("model", config.get("culprit_model", "") if config else ""),
                "victim_model_id": victim_msg.get("model", config.get("victim_model", "") if config else ""),
                "culprit_message_length": len(culprit_msg.get("message", "")),
                "victim_message_length": len(victim_msg.get("message", "")),
                "culprit_timestamp": culprit_msg.get("timestamp", ""),
                "victim_timestamp": victim_msg.get("timestamp", ""),
                "verdict_given_usd": verdict.get("given_usd", 0),
                "verdict_transaction_type": verdict.get("transaction_type", "none"),
                "verdict_confidence": verdict.get("confidence", 1.0),
                "cumulative_before": verdict.get("cumulative_before", 0),
                "cumulative_after": verdict.get("cumulative_before", 0) + verdict.get("given_usd", 0),
            })
    
    return rows


def build_arbiter_verdicts_table() -> list[dict]:
    """Build arbiter_verdicts.csv from all arbiter.jsonl files."""
    rows = []
    
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        
        game_id = game_dir.name
        config = load_json(game_dir / "config.json")
        verdicts = load_jsonl(game_dir / "arbiter.jsonl")
        
        for v in verdicts:
            rows.append({
                "game_id": game_id,
                "victim_turn": v.get("victim_turn", 0),
                "arbiter_model_id": config.get("arbiter_model", "") if config else "",
                "given_usd": v.get("given_usd", 0),
                "transaction_type": v.get("transaction_type", "none"),
                "confidence": v.get("confidence", 1.0),
                "reasoning": v.get("reasoning", ""),
                "evidence_quote": v.get("evidence_quote", ""),
                "cumulative_before": v.get("cumulative_before", 0),
                "timestamp": v.get("timestamp", ""),
                "raw_response": v.get("raw_response", ""),
            })
    
    return rows


def build_transfers_table() -> list[dict]:
    """Build transfers.csv from all ledger.jsonl files."""
    rows = []
    
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        
        game_id = game_dir.name
        ledger = load_jsonl(game_dir / "ledger.jsonl")
        
        for entry in ledger:
            rows.append({
                "game_id": game_id,
                "turn": entry.get("turn", 0),
                "delta_usd": entry.get("delta_usd", 0),
                "remaining_usd": entry.get("remaining_usd", 0),
                "timestamp": entry.get("timestamp", ""),
            })
    
    return rows


def build_elo_history_table() -> list[dict]:
    """Build elo_history.csv from elo_history.jsonl."""
    records = load_jsonl(ELO_HISTORY_FILE)
    rows = []
    
    for i, r in enumerate(records):
        rows.append({
            "record_index": i,
            "game_id": r.get("game_id", ""),
            "model_id": r.get("model", ""),
            "model_short": model_id_to_short_name(r.get("model", "")),
            "role": r.get("role", ""),
            "old_elo": r.get("old_elo", 1500),
            "new_elo": r.get("new_elo", 1500),
            "elo_delta": r.get("new_elo", 1500) - r.get("old_elo", 1500),
            "score": r.get("score", ""),
        })
    
    return rows


def build_elo_final_table() -> list[dict]:
    """Build elo_final.csv from elo_current.json."""
    elo_data = load_json(ELO_CURRENT_FILE) or {}
    rows = []
    
    for model_id, ratings in elo_data.items():
        culprit_elo = ratings.get("culprit", 1500)
        victim_elo = ratings.get("victim", 1500)
        avg_elo = (culprit_elo + victim_elo) / 2
        
        rows.append({
            "model_id": model_id,
            "model_short": model_id_to_short_name(model_id),
            "culprit_elo": round(culprit_elo, 2),
            "victim_elo": round(victim_elo, 2),
            "avg_elo": round(avg_elo, 2),
            "elo_spread": round(victim_elo - culprit_elo, 2),
        })
    
    # Sort by avg_elo descending
    rows.sort(key=lambda x: x["avg_elo"], reverse=True)
    
    # Add rank
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    
    return rows


def build_aggregate_stats() -> list[dict]:
    """Build aggregate_stats.csv - summary statistics."""
    games = build_games_table()
    
    # Per-model stats as culprit
    culprit_stats = defaultdict(lambda: {
        "games_as_culprit": 0,
        "total_extracted": 0,
        "wins_as_culprit": 0,
    })
    
    # Per-model stats as victim
    victim_stats = defaultdict(lambda: {
        "games_as_victim": 0,
        "total_lost": 0,
        "wins_as_victim": 0,
    })
    
    for g in games:
        if not g["is_complete"]:
            continue
        
        culprit = g["culprit_model_id"]
        victim = g["victim_model_id"]
        extracted = g["extracted_usd"]
        
        culprit_stats[culprit]["games_as_culprit"] += 1
        culprit_stats[culprit]["total_extracted"] += extracted
        if g["outcome"] == "culprit_win":
            culprit_stats[culprit]["wins_as_culprit"] += 1
        
        victim_stats[victim]["games_as_victim"] += 1
        victim_stats[victim]["total_lost"] += extracted
        if g["outcome"] == "victim_win":
            victim_stats[victim]["wins_as_victim"] += 1
    
    # Merge into rows
    all_models = set(culprit_stats.keys()) | set(victim_stats.keys())
    rows = []
    
    for model_id in all_models:
        cs = culprit_stats[model_id]
        vs = victim_stats[model_id]
        
        games_culprit = cs["games_as_culprit"]
        games_victim = vs["games_as_victim"]
        
        rows.append({
            "model_id": model_id,
            "model_short": model_id_to_short_name(model_id),
            "total_games": games_culprit + games_victim,
            "games_as_culprit": games_culprit,
            "games_as_victim": games_victim,
            "total_extracted_as_culprit": round(cs["total_extracted"], 2),
            "total_lost_as_victim": round(vs["total_lost"], 2),
            "avg_extraction_as_culprit": round(cs["total_extracted"] / games_culprit, 2) if games_culprit > 0 else 0,
            "avg_loss_as_victim": round(vs["total_lost"] / games_victim, 2) if games_victim > 0 else 0,
            "wins_as_culprit": cs["wins_as_culprit"],
            "wins_as_victim": vs["wins_as_victim"],
            "win_rate_culprit": round(cs["wins_as_culprit"] / games_culprit, 3) if games_culprit > 0 else 0,
            "win_rate_victim": round(vs["wins_as_victim"] / games_victim, 3) if games_victim > 0 else 0,
        })
    
    rows.sort(key=lambda x: x["total_games"], reverse=True)
    return rows


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("\n" + "=" * 60)
    print(" AREG DATASET GENERATOR")
    print("=" * 60)
    print(f"\nSource: {GAMES_DIR}")
    print(f"Output: {OUTPUT_DIR}\n")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Models
    print("📋 Building models.csv...")
    models = build_models_table()
    write_csv(OUTPUT_DIR / "models.csv", [
        "model_id", "model_name", "provider", "short_name",
        "context_window", "parameters", "release_date", "knowledge_cutoff",
        "input_price_per_1m", "output_price_per_1m",
        "architecture", "modalities", "use_case", "special_features",
        "benchmark_mmlu", "benchmark_gpqa", "benchmark_humaneval", "benchmark_gsm8k", "benchmark_math"
    ], models, text_fields=["architecture", "modalities", "use_case", "special_features"])
    
    # 2. Games
    print("\n🎮 Building games.csv...")
    games = build_games_table()
    write_csv(OUTPUT_DIR / "games.csv", [
        "game_id", "date", "round",
        "culprit_model_id", "victim_model_id", "arbiter_model_id",
        "culprit_short", "victim_short", "arbiter_short",
        "initial_usd", "max_turns", "started_at", "completed_at",
        "total_turns", "extracted_usd", "remaining_usd", "extraction_ratio",
        "outcome", "is_complete",
        "total_message_chars", "culprit_chars", "victim_chars", "turns_with_extraction"
    ], games)
    
    # 3. Messages
    print("\n💬 Building messages.csv...")
    messages = build_messages_table()
    write_csv(OUTPUT_DIR / "messages.csv", [
        "game_id", "message_index", "turn", "role",
        "model_id", "model_short", "message", "message_length", "timestamp"
    ], messages, text_fields=["message"])
    
    # 4. Turns
    print("\n🔄 Building turns.csv...")
    turns = build_turns_table()
    write_csv(OUTPUT_DIR / "turns.csv", [
        "game_id", "turn",
        "culprit_model_id", "victim_model_id",
        "culprit_message_length", "victim_message_length",
        "culprit_timestamp", "victim_timestamp",
        "verdict_given_usd", "verdict_transaction_type", "verdict_confidence",
        "cumulative_before", "cumulative_after"
    ], turns)
    
    # 5. Arbiter Verdicts
    print("\n⚖️  Building arbiter_verdicts.csv...")
    verdicts = build_arbiter_verdicts_table()
    write_csv(OUTPUT_DIR / "arbiter_verdicts.csv", [
        "game_id", "victim_turn", "arbiter_model_id",
        "given_usd", "transaction_type", "confidence",
        "reasoning", "evidence_quote", "cumulative_before",
        "timestamp", "raw_response"
    ], verdicts, text_fields=["reasoning", "evidence_quote", "raw_response"])
    
    # 6. Transfers
    print("\n💸 Building transfers.csv...")
    transfers = build_transfers_table()
    write_csv(OUTPUT_DIR / "transfers.csv", [
        "game_id", "turn", "delta_usd", "remaining_usd", "timestamp"
    ], transfers)
    
    # 7. Elo History
    print("\n📈 Building elo_history.csv...")
    elo_history = build_elo_history_table()
    write_csv(OUTPUT_DIR / "elo_history.csv", [
        "record_index", "game_id", "model_id", "model_short",
        "role", "old_elo", "new_elo", "elo_delta", "score"
    ], elo_history)
    
    # 8. Final Elo
    print("\n🏆 Building elo_final.csv...")
    elo_final = build_elo_final_table()
    write_csv(OUTPUT_DIR / "elo_final.csv", [
        "rank", "model_id", "model_short",
        "culprit_elo", "victim_elo", "avg_elo", "elo_spread"
    ], elo_final)
    
    # 9. Aggregate Stats
    print("\n📊 Building aggregate_stats.csv...")
    stats = build_aggregate_stats()
    write_csv(OUTPUT_DIR / "aggregate_stats.csv", [
        "model_id", "model_short", "total_games",
        "games_as_culprit", "games_as_victim",
        "total_extracted_as_culprit", "total_lost_as_victim",
        "avg_extraction_as_culprit", "avg_loss_as_victim",
        "wins_as_culprit", "wins_as_victim",
        "win_rate_culprit", "win_rate_victim"
    ], stats)
    
    # Summary
    complete_games = sum(1 for g in games if g["is_complete"])
    total_messages = len(messages)
    total_chars = sum(m["message_length"] for m in messages)
    
    print("\n" + "=" * 60)
    print(" DATASET SUMMARY")
    print("=" * 60)
    print(f"""
  📁 Output directory: {OUTPUT_DIR}
  
  📊 Statistics:
     • Models:           {len(models)}
     • Games (total):    {len(games)}
     • Games (complete): {complete_games}
     • Messages:         {total_messages}
     • Total characters: {total_chars:,}
     • Turns:            {len(turns)}
     • Arbiter verdicts: {len(verdicts)}
     • Elo updates:      {len(elo_history)}
  
  📄 Generated files:
     • models.csv            - Model metadata
     • games.csv             - Game summaries
     • messages.csv          - Full conversation text
     • turns.csv             - Turn-level aggregates
     • arbiter_verdicts.csv  - Arbiter judgments
     • transfers.csv         - Money transfer events
     • elo_history.csv       - Rating changes
     • elo_final.csv         - Final rankings
     • aggregate_stats.csv   - Per-model statistics
""")
    print("=" * 60)
    print(" ✅ Dataset generation complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
