"""Local API server that answers on both loopback addresses (docs/45).

    uv run python -m app.devserver [--port 8000]

On Windows `localhost` resolves to ::1 first. `uvicorn --port 8000` listens on 127.0.0.1 only, so every new
connection from the browser (or Next's server) to http://localhost:8000 first knocks on ::1, is refused and
falls back to IPv4: +0.17-0.2 s per connection, 2 s for Python clients. Listening on both removes it.
Still loopback only (nothing is exposed to the network). Deployments keep their own uvicorn command.
"""

from __future__ import annotations

import argparse
import socket

import uvicorn


def _listen(family: socket.AddressFamily, host: str, port: int) -> socket.socket | None:
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    sock.set_inheritable(True)
    return sock


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    sockets = [
        s
        for s in (_listen(socket.AF_INET, "127.0.0.1", args.port), _listen(socket.AF_INET6, "::1", args.port))
        if s is not None
    ]
    if not sockets:
        raise SystemExit(f"port {args.port} is taken")
    server = uvicorn.Server(uvicorn.Config("app.main:app", port=args.port))
    server.run(sockets=sockets)


if __name__ == "__main__":
    main()
