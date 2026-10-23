"""Lectern development entry point.

All server code lives in the server/ package; this file only provides the
`python app.py` runner. Open http://localhost:5003/ (localhost counts as a
secure page, so it works without HTTPS there; anywhere else Lectern insists on HTTPS).

Accounts are invite-only. Make the first (admin) one with
    python app.py invite you@example.com --admin
and open the link it prints. Settings go in a .env file beside this one (see
.env.example and README.md), or in the environment.
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
    import sys
    from server import cli
    if len(sys.argv) > 1 and sys.argv[1] in cli.COMMANDS:
        cli.main(sys.argv[1:])
        sys.exit(0)
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.environ.get('LECTERN_PORT') or 5003))
    parser.add_argument('--host', default='127.0.0.1',
                        help='Use 0.0.0.0 to reach it from other machines (then it must be behind HTTPS: see the README).')
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)
