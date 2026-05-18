import argparse
import os
import math
import sys
from pathlib import Path

import chess.engine
import chess.pgn as pgn
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

PGN_DIR = Path("pgns")
OUTPUT_DIR = Path("outputs")


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze a chess PGN using stockfish")
    parser.add_argument("filename", help="PGN filename inside the PGNS/ folder")
    parser.add_argument(
        "--depth", type=int, default=12, help="Stockfish analysis depth. Default: 12"
    )
    parser.add_argument("--player", help="Player username/name from PGN headers")
    parser.add_argument(
        "--threshold",
        type=int,
        default=150,
        help="Minimum centipawn loss to mark a mistake. Default: 150",
    )
    parser.add_argument("--no-ai", action="store_true", help="Skip Groq AI explanation")
    parser.add_argument(
        "--save", action="store_true", help="Save analysis report to outputs/"
    )
    return parser.parse_args()


def load_pgn(filename):
    """Load the pgn file as chess object"""
    try:
        path = PGN_DIR / filename

        with open(path, "r") as f:
            game = pgn.read_game(f)

        return game
    except FileNotFoundError:
        return None


def classify_severity(loss):
    if loss >= 300:
        return "Blunder"
    elif loss >= 150:
        return "Mistake"
    elif loss >= 75:
        return "Inaccuracy"
    else:
        return "Okay"

def calculate_win_percent(centipawns):
    multiplier = -0.00368208
    return 50 + 50 * (2/(1 + math.exp(multiplier * centipawns)) - 1)
    
def calculate_accuracy(centipawns_before, centipawns_after):
    if(centipawns_after >= centipawns_before): return 100.0
    win_percent_before = calculate_win_percent(centipawns_before)
    win_percent_after = calculate_win_percent(centipawns_after)
    
    win_diff = win_percent_before - win_percent_after

    accuracy_percent = 103.1668100711649 * math.exp(-0.04354415386753951 * win_diff) + -3.166924740191411

    return max(0.0, min(100.0, accuracy_percent))

def find_blunders(game, player, depth=12, threshold=150):
    engine = None
    move_accuracies = []
    try:
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        board = game.board()
        blunders = []

        for i, move in enumerate(game.mainline_moves(), start=1):
            turn = "white" if board.turn == chess.WHITE else "black"
            san = board.san(move)
            move_no = board.fullmove_number

            info = engine.analyse(board, limit=chess.engine.Limit(depth=depth))
            before_score = info["score"].white().score(mate_score=100000)

            best_move = (
                board.san(info["pv"][0]) if "pv" in info and info["pv"] else None
            )

            board.push(move)

            after_info = engine.analyse(board, limit=chess.engine.Limit(depth=depth))
            after_score = after_info["score"].white().score(mate_score=100000)

            if before_score is None or after_score is None:
                continue

            
            if turn == player:
                if turn == "white":
                    cp_before = before_score
                    cp_after = after_score
                    loss = -(after_score - before_score)
                else:
                    cp_before = before_score * -1
                    cp_after = after_score * -1
                    loss = after_score - before_score

                move_acc = calculate_accuracy(cp_before, cp_after)
                move_accuracies.append(move_acc)

                severity = classify_severity(loss)

                if loss >= threshold:
                    print(
                        f"Analyzing move {i}: {move_no}{'...' if turn == 'black' else '.'} {san}"
                    )
                    print(
                        f"{move_no:<4} | {san:<8} | {str(best_move):<8} | "
                        f"{before_score:<7} | {after_score:<7} | {loss:<6} | {move_acc:.1f}% | {severity}"
                    )
                    blunders.append(
                        {
                            "move": san,
                            "move_no": move_no,
                            "before": before_score,
                            "after": after_score,
                            "best_move": best_move,
                            "loss": loss,
                            "accuracy": move_acc,
                            "severity": severity,
                            "fen": board.fen(),
                        }
                    )

        overall_accuracy = 100.0
        if move_accuracies:
            harmonic = len(move_accuracies)/sum(1.0/ max(0.01,i) for i in move_accuracies)
            arithmetic = sum(move for move in move_accuracies)/len(move_accuracies)
            overall_accuracy = round((harmonic+arithmetic)/2, 2)
        return blunders, overall_accuracy

    finally:
        if engine:
            engine.quit()


def build_summary(blunders, depth, threshold):
    if not blunders:
        return f"No mistakes above {threshold}cp found at depth {depth}."

    inaccuracies = sum(1 for b in blunders if b["severity"] == "Inaccuracy")
    mistakes = sum(1 for b in blunders if b["severity"] == "Mistake")
    blunder_count = sum(1 for b in blunders if b["severity"] == "Blunder")

    worst = max(blunders, key=lambda b: b["loss"])
    average_loss = sum(b["loss"] for b in blunders) / len(blunders)

    summary = f"""
Summary
-------
Total issues found: {len(blunders)}
Inaccuracies: {inaccuracies}
Mistakes: {mistakes}
Blunders: {blunder_count}
Worst move: {worst["move_no"]}. {worst["move"]}, loss {worst["loss"]}cp
Average loss: {average_loss:.1f}cp
Depth used: {depth}
Threshold: {threshold}cp
"""

    return summary


def build_issue_table(blunders):
    if not blunders:
        return "No engine-detected issues."

    lines = []
    lines.append("Move | Played   | Best     | Before  | After   | Loss   | Accuracy   | Severity")
    lines.append("-" * 75)

    for b in blunders:
        lines.append(
            f"{b['move_no']:<4} | {b['move']:<8} | {str(b['best_move']):<8} | "
            f"{b['before']:<7} | {b['after']:<7} | {b['loss']:<6} | {b['accuracy']:9.1f}% | {b['severity']}"
        )

    return "\n".join(lines)


def build_prompt(blunders, game, player):
    lines = []
    for b in blunders:
        line = f"- Move {b['move_no']}: {b['move']} [{b['severity']}] (best was {b['best_move']}, FEN: {b['fen']}, eval changed from {b['before']:+} to {b['after']:+}, loss: {b['loss']}cp)"
        lines.append(line)
    lines = "\n".join(lines)
    header = f"""Game: {game.headers["White"]} vs {game.headers["Black"]}
Player: {player}

Engine-detected issues:
"""
    footer = """

    For each issue, explain in 2-3 lines:
    1. What the player probably missed
    2. Why the suggested move was better
    3. One practical lesson
    """
    prompt = header + lines + footer
    return prompt


def analyze_game(prompt):
    try:
        client = Groq(
            api_key=os.environ.get("GROQ_API_KEY"),
        )
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a chess coach. Analyze blunders clearly and concisely.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        raise ValueError(f"Groq API error: {e}")


if __name__ == "__main__":
    args = parse_args()

    game = load_pgn(args.filename)
    if not game:
        print("File not found")
        sys.exit(1)

    username = args.player
    if not username:
        username = input("Enter your username: ")

    white = game.headers.get("White", "").strip().lower()
    black = game.headers.get("Black", "").strip().lower()
    username = username.strip().lower()

    if username == white:
        player = "white"
    elif username == black:
        player = "black"
    else:
        raise ValueError("Username not found in PGN headers.")

    blunders, accuracy = find_blunders(game, player, depth=args.depth, threshold=args.threshold)
    summary = build_summary(blunders, args.depth, args.threshold)
    print(summary)
    print(f"YOUR OVERALL GAME ACCURACY: {accuracy}% \n")
    issue_table = build_issue_table(blunders)
    print(issue_table)
    print()

    if not blunders:
        sys.exit(0)

    prompt = build_prompt(blunders, game, player)

    if not args.no_ai:
        try:
            ai_analysis = analyze_game(prompt)
            print(ai_analysis)
        except ValueError as e:
            print(e)
            sys.exit(1)
    else:
        ai_analysis = "AI explanation skipped."
        print(ai_analysis)

    if args.save:
        OUTPUT_DIR.mkdir(exist_ok=True)

        output_path = OUTPUT_DIR / f"{Path(args.filename).stem}_analysis.txt"

        with open(output_path, "w") as f:
            f.write(summary)
            f.write("\n\nRaw Engine Table:\n")
            f.write(issue_table)
            f.write("\n\nEngine Findings:\n")
            f.write(prompt)
            f.write("\n\nAI Coach Analysis:\n")
            f.write(ai_analysis)

        print(f"Saved report to {output_path}")
