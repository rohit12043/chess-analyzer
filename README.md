# Chess Game Analyzer

Analyzes the user's game, finds blunders and adds a layer of explainability to it.

## How it works

<img width="1365" height="469" alt="architecture" src="https://github.com/user-attachments/assets/5b3b3047-c978-4fcf-b9bc-980f4570c8cb" />

## Requirements

Python 3.x
Stockfish installed (sudo apt install stockfish / download from stockfishchess.org)
Groq API key (free at console.groq.com)

## Setup

```bash
git clone https://github.com/rohit12043/chess-analyzer
cd chess-analyzer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "GROQ_API_KEY=your_key" > .env
```

## Usage

```bash
python main.py your_game.pgn
```

Then enter your username when prompted.

## Example output

<img width="1517" height="155" alt="image" src="https://github.com/user-attachments/assets/1eab14b2-d99a-4573-85eb-ceb001668b17" />

## Why I built this

I play chess, and I want to understand my blunders, but who's got money for Chess.com premium ¯\\_(ツ)_/¯
