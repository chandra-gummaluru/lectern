"""Lectern development entry point.

All server code lives in the server/ package; this file only provides the
`python app.py` runner. Open http://localhost:5002/ (localhost counts as a
secure page, so "Choose a folder" works without HTTPS).

Sign in with GitHub needs the GitHub App's settings: put them in a .env file
beside this one (see .env.example and README.md), or in the environment.
Without them, the folder mode still works.
"""
import os


def _load_env(path):
    """Settings from a .env file beside this one (KEY=value per line), so they needn't be set each time.
    Values already in the environment win. The file holds the client secret: it's in .gitignore."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from server import app  # noqa: E402,F401

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5002)
    parser.add_argument('--host', default='127.0.0.1',
                        help='Use 0.0.0.0 to reach it from other machines (sign-in then needs LECTERN_APP_URL).')
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)
