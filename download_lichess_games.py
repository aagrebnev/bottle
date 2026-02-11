#!/usr/bin/env python
"""Download the last N games of a Lichess user in PGN format.

Usage:
    python download_lichess_games.py [username] [max_games] [output_file]

Defaults:
    username:    agrebneva
    max_games:   20
    output_file: {username}_last{max_games}.pgn
"""

import sys

try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib2 import urlopen, Request


def download_games(username="agrebneva", max_games=20, output_file=None):
    if output_file is None:
        output_file = "{}_last{}.pgn".format(username, max_games)

    url = "https://lichess.org/api/games/user/{}?max={}&clocks=true&opening=true".format(
        username, max_games
    )
    req = Request(url, headers={"Accept": "application/x-chess-pgn"})

    print("Downloading last {} games of {} ...".format(max_games, username))
    response = urlopen(req)
    data = response.read()

    with open(output_file, "wb") as f:
        f.write(data)

    print("Saved to {}  ({} bytes)".format(output_file, len(data)))
    return output_file


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "agrebneva"
    max_games = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    download_games(username, max_games, output_file)
