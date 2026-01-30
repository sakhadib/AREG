"""
AREG Tournament Runner
Round-robin tournament across all models in models.json.

Usage:
    python tournament.py --ar google/gemini-2.5-flash-lite

All state is persisted to disk. Tournament can be resumed at any point.
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from itertools import permutations

from run import run_game, load_json, save_json, append_jsonl, get_elo, ELO_DIR

BASE_DIR = Path(__file__).parent
MODELS_PATH = BASE_DIR / "models" / "models.json"
TOURNAMENT_DIR = BASE_DIR / "tournaments"


def load_models() -> list:
    """Load all models from models.json."""
    with open(MODELS_PATH, "r", encoding="utf-8") as f:
        models = json.load(f)
    return [m["model_id"] for m in models]


def generate_game_id(culprit_id: str, victim_id: str, round_num: int = 1) -> str:
    """Generate deterministic game ID from model pair and round."""
    # Use short names for readability
    c_short = culprit_id.split("/")[-1]
    v_short = victim_id.split("/")[-1]
    date = datetime.now().strftime("%Y-%m-%d")
    if round_num > 1:
        return f"{date}_R{round_num}_{c_short}_vs_{v_short}"
    return f"{date}_{c_short}_vs_{v_short}"


def print_header(text: str, char: str = "═"):
    width = 60
    print()
    print(char * width)
    print(f" {text}")
    print(char * width)


def print_leaderboard(role: str):
    """Print current Elo leaderboard for a role."""
    elo_data = load_json(ELO_DIR / "elo_current.json")
    
    if not elo_data:
        print("  (No Elo data yet)")
        return
    
    # Collect scores
    scores = []
    for model_id, ratings in elo_data.items():
        if role in ratings:
            scores.append((model_id, ratings[role]))
    
    # Sort by Elo descending
    scores.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n{'Rank':<6}{'Model':<45}{'Elo':>8}")
    print("-" * 60)
    for i, (model_id, elo) in enumerate(scores, 1):
        short_name = model_id.split("/")[-1]
        print(f"{i:<6}{short_name:<45}{elo:>8.0f}")


def run_tournament(arbiter_id: str, round_num: int = 1):
    """
    Run round-robin tournament.
    All pairs: A(C) vs B(V) for all ordered pairs of distinct models.
    """
    # Setup tournament directory
    TOURNAMENT_DIR.mkdir(exist_ok=True)
    
    # Load models
    models = load_models()
    n_models = len(models)
    
    round_label = f" (Round {round_num})" if round_num > 1 else ""
    print_header(f"AREG TOURNAMENT{round_label}")
    print(f"\n📋 Models loaded: {n_models}")
    for m in models:
        print(f"   • {m}")
    
    print(f"\n⚖️  Arbiter: {arbiter_id}")
    
    # Generate all ordered pairs (permutations)
    pairs = list(permutations(models, 2))
    total_games = len(pairs)
    
    print(f"\n🎮 Total games: {total_games}")
    print_header("STARTING GAMES", "─")
    
    # Tournament state file (include round number)
    tournament_id = datetime.now().strftime("%Y-%m-%d")
    if round_num > 1:
        state_path = TOURNAMENT_DIR / f"{tournament_id}_R{round_num}_state.json"
        results_path = TOURNAMENT_DIR / f"{tournament_id}_R{round_num}_results.jsonl"
    else:
        state_path = TOURNAMENT_DIR / f"{tournament_id}_state.json"
        results_path = TOURNAMENT_DIR / f"{tournament_id}_results.jsonl"
    
    # Load or initialize tournament state
    if state_path.exists():
        tournament_state = load_json(state_path)
        completed_games = set(tournament_state.get("completed_games", []))
        print(f"\n♻️  Resuming tournament. {len(completed_games)}/{total_games} games completed.")
    else:
        tournament_state = {
            "tournament_id": f"{tournament_id}_R{round_num}" if round_num > 1 else tournament_id,
            "round": round_num,
            "arbiter": arbiter_id,
            "total_games": total_games,
            "completed_games": [],
            "started_at": datetime.now().isoformat()
        }
        completed_games = set()
        save_json(state_path, tournament_state)
    
    # Run games
    games_played = 0
    games_skipped = 0
    
    for i, (culprit_id, victim_id) in enumerate(pairs, 1):
        game_id = generate_game_id(culprit_id, victim_id, round_num)
        
        print(f"\n[{i}/{total_games}] ", end="")
        
        if game_id in completed_games:
            print(f"⏭️  Skipping (already completed): {game_id}")
            games_skipped += 1
            continue
        
        c_short = culprit_id.split("/")[-1]
        v_short = victim_id.split("/")[-1]
        print(f"🎮 {c_short} (C) vs {v_short} (V)")
        
        try:
            result = run_game(
                culprit_id=culprit_id,
                victim_id=victim_id,
                arbiter_id=arbiter_id,
                game_id=game_id
            )
            
            # Mark as completed immediately
            completed_games.add(game_id)
            tournament_state["completed_games"] = list(completed_games)
            save_json(state_path, tournament_state)
            
            # Append to results
            append_jsonl(results_path, result)
            
            games_played += 1
            
        except KeyboardInterrupt:
            print("\n\n⛔ Tournament interrupted by user. Progress saved.")
            print(f"   Completed: {len(completed_games)}/{total_games} games")
            raise SystemExit(0)
        except Exception as e:
            print(f"\n❌ Error in game {game_id}: {e}")
            print("   Continuing to next game...")
            continue
    
    # Final summary
    print_header("TOURNAMENT COMPLETE", "═")
    print(f"\n📊 Summary:")
    print(f"   Total games:    {total_games}")
    print(f"   Games played:   {games_played}")
    print(f"   Games skipped:  {games_skipped}")
    
    # Update tournament state
    tournament_state["completed_at"] = datetime.now().isoformat()
    tournament_state["games_played"] = games_played
    save_json(state_path, tournament_state)
    
    # Print leaderboards
    print_header("CULPRIT LEADERBOARD (Persuasion)")
    print_leaderboard("culprit")
    
    print_header("VICTIM LEADERBOARD (Resistance)")
    print_leaderboard("victim")
    
    # Print combined score
    print_header("COMBINED RANKINGS")
    elo_data = load_json(ELO_DIR / "elo_current.json")
    
    if elo_data:
        combined = []
        for model_id, ratings in elo_data.items():
            c_elo = ratings.get("culprit", 1500)
            v_elo = ratings.get("victim", 1500)
            avg_elo = (c_elo + v_elo) / 2
            combined.append((model_id, c_elo, v_elo, avg_elo))
        
        combined.sort(key=lambda x: x[3], reverse=True)
        
        print(f"\n{'Rank':<6}{'Model':<35}{'C-Elo':>8}{'V-Elo':>8}{'Avg':>8}")
        print("-" * 70)
        for i, (model_id, c_elo, v_elo, avg_elo) in enumerate(combined, 1):
            short_name = model_id.split("/")[-1]
            print(f"{i:<6}{short_name:<35}{c_elo:>8.0f}{v_elo:>8.0f}{avg_elo:>8.0f}")
    
    print("\n✅ Tournament data saved to:", TOURNAMENT_DIR)
    print("✅ Elo data saved to:", ELO_DIR)


def main():
    parser = argparse.ArgumentParser(description="AREG Tournament Runner")
    parser.add_argument("--ar", required=True, help="Arbiter model ID (e.g., google/gemini-2.5-flash)")
    parser.add_argument("--rounds", type=int, default=1, help="Number of tournament rounds to run (default: 1)")
    parser.add_argument("--start-round", type=int, default=1, help="Starting round number (default: 1)")
    
    args = parser.parse_args()
    
    start_round = args.start_round
    end_round = start_round + args.rounds - 1
    
    for round_num in range(start_round, end_round + 1):
        print(f"\n{'='*60}")
        print(f" 🔄 STARTING ROUND {round_num} OF {end_round}")
        print(f"{'='*60}")
        
        try:
            run_tournament(arbiter_id=args.ar, round_num=round_num)
        except KeyboardInterrupt:
            print(f"\n\n⛔ Interrupted during round {round_num}. Progress saved.")
            raise SystemExit(0)
    
    print(f"\n{'='*60}")
    print(f" 🏆 ALL {args.rounds} ROUND(S) COMPLETE!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
