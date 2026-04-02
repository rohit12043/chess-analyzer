import sys
from pathlib import Path
import chess.pgn as pgn
import chess.engine

PGN_DIR = Path("pgns")

def load_pgn(filename):
    """Load the pgn file as chess object"""
    path = PGN_DIR / filename
    
    with open(path, "r") as f:
        game = pgn.read_game(f)
    
    return game

def find_blunders(game, player):
    try:
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        board = game.board()
        blunders = []
        for move in game.mainline_moves():
            turn = "white" if board.turn else "black"
            san = board.san(move)
            before_score = engine.analyse(board, limit=chess.engine.Limit(depth=10))["score"].white().score()
            board.push(move)
            after_score = engine.analyse(board, limit=chess.engine.Limit(depth=10))["score"].white().score()
            
            if before_score is None or after_score is None:
                continue
            diff = after_score - before_score
            if((turn == player and turn == "white" and abs(after_score - before_score) > 150 and after_score < before_score) or (turn == player and turn == "black" and abs(after_score - before_score) > 150 and after_score > before_score)):
                blunders.append({
                    "move": san,
                    "move_no": board.fullmove_number,
                    "before": before_score,
                    "after": after_score,
                    "diff": diff,
                    "fen": board.fen()
                })
    finally:
        engine.quit()
    return blunders
    
def build_prompt(blunders, game, player):
    lines = []
    for b in blunders:
        line = f"- Move {b['move_no']}: {b['move']}, FEN: {b['fen']} (eval dropped from {b['before']:+} to {b['after']:+}, dropped by {abs(b['diff'])} centipawns)"
        lines.append(line)
    lines = "\n".join(lines)
    header = f"""Game: {game.headers["White"]} vs {game.headers["Black"]}
Player: {player}
    
Blunders:
"""
    footer = """
    \nFor each blunder explain in 2-3 lines: what went wrong and what the better idea was.
    """
    prompt = header + lines + footer
    return prompt

if __name__ == "__main__":
    filename = sys.argv[1]
    game = load_pgn(filename)
    username = input("Enter your username: ")
    Player = "white" if username == game.headers["White"] else "black"
    blunders = find_blunders(game, Player)
    prompt = build_prompt(blunders, game, Player)
    print(prompt)