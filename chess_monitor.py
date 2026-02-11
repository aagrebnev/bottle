#!/usr/bin/env python
"""
Chess Telegram Monitor for Lichess

Monitors a Lichess player's games in real-time and sends move updates
with Stockfish analysis to a Telegram chat.

Usage:
    python chess_monitor.py <lichess_username>

Environment variables:
    TELEGRAM_BOT_TOKEN  - Telegram Bot API token (required)
    TELEGRAM_CHAT_ID    - Telegram chat ID to send messages to (required)
    STOCKFISH_PATH      - Path to Stockfish binary (default: "stockfish")
"""

import io
import os
import re
import sys
import json
import time
import logging

import cairosvg
import requests
import chess
import chess.engine
import chess.svg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "stockfish")

LICHESS_BASE = "https://lichess.org"
LICHESS_CURRENT_GAME = LICHESS_BASE + "/api/user/{username}/current-game"
LICHESS_STREAM_GAME = LICHESS_BASE + "/api/stream/game/{game_id}"

TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_URL = "https://api.telegram.org/bot{token}/sendPhoto"

STOCKFISH_DEPTH = 12
STOCKFISH_MULTIPV = 3

POLL_INTERVAL = 10  # seconds between checks when no game is active
GAME_POLL_INTERVAL = 0.5  # seconds between move checks during a game

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("chess_monitor")

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------


def send_telegram_message(text):
    """Send an HTML-formatted message to the configured Telegram chat.

    Returns True on success, False on failure. Never raises — a Telegram
    failure must not crash the monitor.
    """
    url = TELEGRAM_SEND_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error("Telegram send failed (%s): %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        logger.error("Telegram send error: %s", exc)
    return False


def send_telegram_photo(image_bytes, caption=""):
    """Send a PNG image with an HTML-formatted caption to Telegram.

    *image_bytes* is the raw PNG content as a bytes object.
    Returns True on success, False on failure. Never raises.
    """
    url = TELEGRAM_PHOTO_URL.format(token=TELEGRAM_BOT_TOKEN)
    files = {
        "photo": ("board.png", io.BytesIO(image_bytes), "image/png"),
    }
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, data=data, files=files, timeout=15)
        if resp.status_code == 200:
            return True
        logger.error("Telegram photo send failed (%s): %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        logger.error("Telegram photo send error: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Score formatting
# ---------------------------------------------------------------------------


def format_score(pov_score, from_white=True):
    """Convert a PovScore to a human-readable string.

    If *from_white* is True the score is shown from White's perspective;
    otherwise from the perspective of the side that owns the score.
    """
    score = pov_score.white() if from_white else pov_score
    if score.is_mate():
        mate_in = score.mate()
        return f"#{mate_in}" if mate_in > 0 else f"#{mate_in}"
    cp = score.score()
    if cp is None:
        return "?"
    return f"{cp / 100:+.2f}"


# ---------------------------------------------------------------------------
# Board visualization
# ---------------------------------------------------------------------------


def format_board_text(board):
    """Return a text board diagram wrapped in <pre> tags for Telegram (fallback)."""
    return "<pre>\n" + str(board.unicode(borders=True)) + "\n</pre>"


def generate_board_image(board, player_color, analysis, last_move=None):
    """Generate a PNG image of the board with arrows for the best moves.

    Returns PNG image as bytes, or None on failure.
    """
    arrow_colors = ["green", "#cccc00cc", "#0088ccaa"]
    arrows = []

    if analysis["side_to_move"] == player_color:
        # Player's turn: show their top 3 candidate moves
        for i, line in enumerate(analysis["current_lines"][:3]):
            try:
                move = board.parse_san(line["move_san"])
                color = arrow_colors[i]
                arrows.append(chess.svg.Arrow(move.from_square, move.to_square, color=color))
            except (ValueError, KeyError):
                pass
    else:
        # Opponent's turn: show expected opponent move as red arrow
        if analysis["current_lines"]:
            try:
                opp_move = board.parse_san(analysis["current_lines"][0]["move_san"])
                arrows.append(chess.svg.Arrow(opp_move.from_square, opp_move.to_square, color="red"))
            except (ValueError, KeyError):
                pass

    try:
        svg_data = chess.svg.board(
            board,
            orientation=player_color,
            lastmove=last_move,
            arrows=arrows,
            size=400,
            coordinates=True,
        )
        png_bytes = cairosvg.svg2png(
            bytestring=svg_data.encode("utf-8"),
            output_width=800,
        )
        return png_bytes
    except Exception as exc:
        logger.error("Board image generation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Plain English move descriptions
# ---------------------------------------------------------------------------

_PIECE_NAMES = {
    "N": "Knight",
    "B": "Bishop",
    "R": "Rook",
    "Q": "Queen",
    "K": "King",
}


def san_to_english(san):
    """Convert a SAN move string to a plain-English description.

    Examples:
        "Nf3"     -> "Knight to f3"
        "Bxe5"    -> "Bishop captures on e5"
        "exd5"    -> "e-pawn captures on d5"
        "e4"      -> "Pawn to e4"
        "O-O"     -> "Castle kingside"
        "O-O-O"   -> "Castle queenside"
        "e8=Q+"   -> "Pawn to e8 promoting to Queen, check"
    """
    stripped = san.rstrip("+#")
    suffix = ""
    if san.endswith("#"):
        suffix = ", checkmate"
    elif san.endswith("+"):
        suffix = ", check"

    if stripped in ("O-O", "0-0"):
        return "Castle kingside" + suffix
    if stripped in ("O-O-O", "0-0-0"):
        return "Castle queenside" + suffix

    m = re.match(
        r"^([NBRQK])?([a-h]?[1-8]?)(x)?([a-h][1-8])(?:=([NBRQK]))?[+#]?$",
        san,
    )
    if not m:
        return san

    piece_letter, disambig, capture, dest, promotion = m.groups()

    if piece_letter:
        piece_name = _PIECE_NAMES[piece_letter]
    else:
        if capture:
            piece_name = f"{disambig}-pawn" if disambig else "Pawn"
        else:
            piece_name = "Pawn"

    if capture:
        action = f"captures on {dest}"
    else:
        action = f"to {dest}"

    parts = [piece_name, action]

    if promotion:
        promo_name = _PIECE_NAMES.get(promotion, promotion)
        parts.append(f"promoting to {promo_name}")

    return " ".join(parts) + suffix


# ---------------------------------------------------------------------------
# Stockfish engine manager
# ---------------------------------------------------------------------------


class EngineManager:
    """Manages the Stockfish engine lifecycle with auto-restart."""

    def __init__(self, path):
        self.path = path
        self.engine = None
        self._start()

    def _start(self):
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path)
        logger.info("Stockfish engine started (%s)", self.path)

    def analyse(self, board, limit, multipv=1):
        try:
            return self.engine.analyse(board, limit, multipv=multipv)
        except chess.engine.EngineTerminatedError:
            logger.warning("Engine terminated unexpectedly — restarting")
            self._start()
            return self.engine.analyse(board, limit, multipv=multipv)

    def quit(self):
        if self.engine:
            try:
                self.engine.quit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Position analysis
# ---------------------------------------------------------------------------


def analyze_position(engine_mgr, board):
    """Analyse the current position with Stockfish.

    Returns a dict with:
      eval_score       — evaluation string from White's perspective
      side_to_move     — chess.WHITE or chess.BLACK
      current_lines    — top 3 lines for the side to move
      response_lines   — top 3 lines for the other side (after best move)

    Each line is a dict: {"move_san": str, "score": str, "pv_san": [str]}
    """
    limit = chess.engine.Limit(depth=STOCKFISH_DEPTH)

    # Top 3 lines for the side to move
    results = engine_mgr.analyse(board, limit, multipv=STOCKFISH_MULTIPV)
    if not isinstance(results, list):
        results = [results]

    side_to_move = board.turn
    current_lines = []
    for info in results:
        pv = info.get("pv", [])
        if not pv:
            continue
        move_san = board.san(pv[0])
        # Build readable PV (first few moves)
        tmp = board.copy()
        pv_san = []
        for m in pv[:5]:
            pv_san.append(tmp.san(m))
            tmp.push(m)
        score_str = format_score(info["score"], from_white=True)
        current_lines.append({
            "move_san": move_san,
            "score": score_str,
            "pv_san": pv_san,
        })

    # Top 3 response lines for the other side
    response_lines = []
    if current_lines:
        best_move = board.parse_san(current_lines[0]["move_san"])
        reply_board = board.copy()
        reply_board.push(best_move)
        if not reply_board.is_game_over():
            reply_results = engine_mgr.analyse(
                reply_board, limit, multipv=STOCKFISH_MULTIPV
            )
            if not isinstance(reply_results, list):
                reply_results = [reply_results]
            for info in reply_results:
                pv = info.get("pv", [])
                if not pv:
                    continue
                move_san = reply_board.san(pv[0])
                tmp = reply_board.copy()
                pv_san = []
                for m in pv[:5]:
                    pv_san.append(tmp.san(m))
                    tmp.push(m)
                score_str = format_score(info["score"], from_white=True)
                response_lines.append({
                    "move_san": move_san,
                    "score": score_str,
                    "pv_san": pv_san,
                })

    # Overall eval from White's perspective
    if results:
        eval_score = format_score(results[0]["score"], from_white=True)
    else:
        eval_score = "?"

    return {
        "eval_score": eval_score,
        "side_to_move": side_to_move,
        "current_lines": current_lines,
        "response_lines": response_lines,
    }


# ---------------------------------------------------------------------------
# Lichess API helpers
# ---------------------------------------------------------------------------


def get_current_game(username):
    """Fetch the user's current game from Lichess.

    Returns the game dict, or None if no game is active.
    Handles rate-limiting (429) and server errors (5xx) with retries.
    """
    url = LICHESS_CURRENT_GAME.format(username=username)
    headers = {"Accept": "application/json"}
    max_retries = 5
    base_delay = 2

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    return None
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                logger.warning("Lichess rate-limited — sleeping 60 s")
                time.sleep(60)
                continue
            if resp.status_code >= 500:
                delay = min(base_delay * (2 ** attempt), 60)
                logger.warning(
                    "Lichess server error %s — retrying in %d s",
                    resp.status_code,
                    delay,
                )
                time.sleep(delay)
                continue
            # Other client errors
            logger.error("Lichess API error %s: %s", resp.status_code, resp.text)
            return None
        except requests.ConnectionError:
            delay = min(base_delay * (2 ** attempt), 60)
            logger.warning("Connection error — retrying in %d s", delay)
            time.sleep(delay)
        except requests.Timeout:
            delay = min(base_delay * (2 ** attempt), 60)
            logger.warning("Request timeout — retrying in %d s", delay)
            time.sleep(delay)

    logger.error("Failed to reach Lichess after %d retries", max_retries)
    return None


# ---------------------------------------------------------------------------
# Player color detection
# ---------------------------------------------------------------------------


def determine_player_color(game_data, username):
    """Return chess.WHITE or chess.BLACK based on the player's side."""
    white_info = game_data.get("players", {}).get("white", {})
    white_user = white_info.get("user", {})
    if white_user.get("id", "").lower() == username.lower():
        return chess.WHITE
    if white_user.get("name", "").lower() == username.lower():
        return chess.WHITE
    return chess.BLACK


def get_player_names(game_data):
    """Return (white_name, black_name) from game data."""
    wp = game_data.get("players", {}).get("white", {})
    bp = game_data.get("players", {}).get("black", {})
    white_name = wp.get("user", {}).get("name", wp.get("user", {}).get("id", "White"))
    black_name = bp.get("user", {}).get("name", bp.get("user", {}).get("id", "Black"))
    return white_name, black_name


def get_player_ratings(game_data):
    """Return (white_rating, black_rating) from game data."""
    wp = game_data.get("players", {}).get("white", {})
    bp = game_data.get("players", {}).get("black", {})
    return wp.get("rating", "?"), bp.get("rating", "?")


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def format_game_start_message(game_data, username, player_color):
    """Build the Telegram message for game start."""
    white_name, black_name = get_player_names(game_data)
    white_rating, black_rating = get_player_ratings(game_data)
    game_id = game_data.get("id", "")
    speed = game_data.get("speed", "?")
    rated = "Yes" if game_data.get("rated") else "No"

    clock = game_data.get("clock", {})
    if clock:
        initial = clock.get("initial", 0) // 60
        increment = clock.get("increment", 0)
        time_control = f"{initial}+{increment}"
    else:
        time_control = "?"

    color_str = "White" if player_color == chess.WHITE else "Black"

    lines = [
        "<b>New Game Started!</b>",
        "",
        f"<b>White:</b> {white_name} ({white_rating})",
        f"<b>Black:</b> {black_name} ({black_rating})",
        f"<b>Time Control:</b> {time_control} ({speed.capitalize()})",
        f"<b>Rated:</b> {rated}",
        f"<b>{username}</b> plays as <b>{color_str}</b>",
        "",
        f"https://lichess.org/{game_id}",
    ]
    return "\n".join(lines)


def format_move_update(
    move_san,
    move_obj,
    half_move_index,
    board,
    player_color,
    username,
    opponent_name,
    analysis,
):
    """Build the Telegram caption and board image for a single move.

    Returns (caption_text, image_bytes_or_none).
    """
    moved_color = not board.turn
    full_move_number = (half_move_index // 2) + 1
    dot = "." if moved_color == chess.WHITE else "..."

    if moved_color == player_color:
        mover_name = username
    else:
        mover_name = opponent_name

    color_word = "White" if moved_color == chess.WHITE else "Black"

    lines = [
        f"<b>Move {full_move_number}{dot} {move_san}</b> by {mover_name} ({color_word})",
        f"<b>Eval:</b> {analysis['eval_score']}",
    ]

    # Show opponent's last move prominently
    if moved_color != player_color:
        english = san_to_english(move_san)
        lines.append("")
        lines.append(f"<b>Opponent played:</b> {move_san} ({english})")

    # Top 3 for the monitored player only
    if analysis["side_to_move"] == player_color:
        player_lines = analysis["current_lines"]
    else:
        player_lines = analysis["response_lines"]

    player_color_word = "White" if player_color == chess.WHITE else "Black"

    lines.append("")
    lines.append(f"<b>Best moves for {username} ({player_color_word}):</b>")
    if player_lines:
        for i, line_info in enumerate(player_lines[:3], 1):
            english = san_to_english(line_info["move_san"])
            lines.append(
                f"  {i}. {line_info['move_san']} - {english}"
                f"  ({line_info['score']})"
            )
    else:
        lines.append("  (no lines available)")

    caption = "\n".join(lines)

    # Generate board image
    image_bytes = generate_board_image(board, player_color, analysis, last_move=move_obj)

    return caption, image_bytes


def format_game_end_message(game_data):
    """Build the Telegram message for game end."""
    game_id = game_data.get("id", "")
    status = game_data.get("status", "unknown")
    winner = game_data.get("winner", None)

    if winner:
        result_str = f"{winner.capitalize()} wins ({status})"
    elif status == "draw":
        result_str = "Draw"
    elif status == "stalemate":
        result_str = "Draw by stalemate"
    else:
        result_str = status.capitalize()

    moves_str = game_data.get("moves", "")
    move_count = len(moves_str.split()) if moves_str else 0

    lines = [
        "<b>Game Over!</b>",
        "",
        f"<b>Result:</b> {result_str}",
        f"<b>Moves played:</b> {move_count}",
        "",
        f"https://lichess.org/{game_id}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Move processing
# ---------------------------------------------------------------------------


def process_new_move(
    board,
    move_san,
    half_move_index,
    player_color,
    username,
    opponent_name,
    engine_mgr,
):
    """Parse a new SAN move, push it, analyse, and send a Telegram message."""
    try:
        move = board.parse_san(move_san)
    except ValueError:
        logger.error("Invalid move '%s' at half-move %d", move_san, half_move_index)
        return

    board.push(move)

    try:
        analysis = analyze_position(engine_mgr, board)
    except Exception as exc:
        logger.error("Stockfish analysis failed: %s", exc)
        analysis = {
            "eval_score": "?",
            "side_to_move": board.turn,
            "current_lines": [],
            "response_lines": [],
        }

    caption, image_bytes = format_move_update(
        move_san,
        move,
        half_move_index,
        board,
        player_color,
        username,
        opponent_name,
        analysis,
    )

    if image_bytes:
        if not send_telegram_photo(image_bytes, caption=caption):
            send_telegram_message(caption + "\n\n" + format_board_text(board))
    else:
        send_telegram_message(caption + "\n\n" + format_board_text(board))

    moved_color = "White" if (not board.turn) == chess.WHITE else "Black"
    logger.info(
        "Move %d: %s (%s) | Eval: %s",
        half_move_index + 1,
        move_san,
        moved_color,
        analysis["eval_score"],
    )


# ---------------------------------------------------------------------------
# Game monitoring
# ---------------------------------------------------------------------------


def monitor_game(game_id, game_data, username, engine_mgr):
    """Monitor a single game from its current state until completion."""
    player_color = determine_player_color(game_data, username)
    white_name, black_name = get_player_names(game_data)

    if player_color == chess.WHITE:
        opponent_name = black_name
    else:
        opponent_name = white_name

    # Send game-start notification
    start_msg = format_game_start_message(game_data, username, player_color)
    send_telegram_message(start_msg)

    # Replay existing moves onto the board
    board = chess.Board()
    moves_str = game_data.get("moves", "")
    known_moves = moves_str.split() if moves_str.strip() else []

    for i, san in enumerate(known_moves):
        try:
            move = board.parse_san(san)
            board.push(move)
        except ValueError:
            logger.error("Failed to replay move %d: '%s'", i, san)
            return

    logger.info(
        "Game %s: replayed %d existing moves, monitoring for new moves",
        game_id,
        len(known_moves),
    )

    # Polling loop for new moves
    while True:
        time.sleep(GAME_POLL_INTERVAL)

        fresh = get_current_game(username)
        if fresh is None:
            # User no longer in a game
            send_telegram_message(format_game_end_message(game_data))
            logger.info("Game %s ended (user no longer in game)", game_id)
            return

        # Make sure it's still the same game
        if fresh.get("id") != game_id:
            send_telegram_message(format_game_end_message(game_data))
            logger.info("Game %s ended (new game detected)", game_id)
            return

        game_data = fresh
        fresh_moves_str = fresh.get("moves", "")
        current_moves = fresh_moves_str.split() if fresh_moves_str.strip() else []

        # Process any new moves
        while len(known_moves) < len(current_moves):
            idx = len(known_moves)
            new_san = current_moves[idx]
            process_new_move(
                board,
                new_san,
                idx,
                player_color,
                username,
                opponent_name,
                engine_mgr,
            )
            known_moves.append(new_san)

        # Check if the game is over
        status = fresh.get("status", "")
        if status not in ("started", "created"):
            send_telegram_message(format_game_end_message(fresh))
            logger.info("Game %s ended with status: %s", game_id, status)
            return


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(username):
    """Continuously monitor a Lichess user for new games."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID environment variable is not set")
        sys.exit(1)

    try:
        engine_mgr = EngineManager(STOCKFISH_PATH)
    except Exception as exc:
        logger.error(
            "Failed to start Stockfish at '%s': %s\n"
            "Install Stockfish (e.g. 'apt install stockfish') "
            "or set the STOCKFISH_PATH environment variable.",
            STOCKFISH_PATH,
            exc,
        )
        sys.exit(1)

    send_telegram_message(
        f"Chess monitor started for <b>{username}</b>\n"
        f"Watching for games on Lichess..."
    )
    logger.info("Monitor started for %s", username)

    current_game_id = None
    try:
        while True:
            game_data = get_current_game(username)
            if game_data and game_data.get("status") in ("started", "created"):
                gid = game_data.get("id")
                if gid != current_game_id:
                    current_game_id = gid
                    logger.info("New game detected: %s", gid)
                    monitor_game(gid, game_data, username, engine_mgr)
                    current_game_id = None
            else:
                logger.debug("No active game — polling in %d s", POLL_INTERVAL)
                time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        send_telegram_message(
            f"Chess monitor stopped for <b>{username}</b>"
        )
        engine_mgr.quit()
        logger.info("Monitor stopped")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <lichess_username>")
        sys.exit(1)
    main(sys.argv[1])
