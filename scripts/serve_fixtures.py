"""在 8899 端口伺服 e2e 静态页面（验证器 / 执行器都指向它）。

    python scripts/serve_fixtures.py
    # http://127.0.0.1:8899/login.html
"""
from __future__ import annotations

import functools
import http.server
import os
import socketserver

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "backend", "fixtures", "web")
PORT = int(os.environ.get("FIXTURE_PORT", "8899"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    handler = functools.partial(Handler, directory=ROOT)
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        print(f"fixtures: http://127.0.0.1:{PORT}/login.html  (dir={ROOT})")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
