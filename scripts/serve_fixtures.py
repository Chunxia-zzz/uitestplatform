"""在 8899 端口伺服 e2e 静态页面（验证器 / 执行器都指向它）。

    python scripts/serve_fixtures.py
    # http://127.0.0.1:8899/login.html

M3.8 起附带两个迷你 API（供网络 mock / 下载冒烟验证"恢复真实内容"与产物取回）：
    GET /api/demo            -> {"ok": true, "msg": "from-real"}
    GET /api/files/report.csv -> attachment 下载（内容 CSV）
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "backend", "fixtures", "web")
PORT = int(os.environ.get("FIXTURE_PORT", "8899"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:  # 基类方法名固定，无法改名
        if self.path.startswith("/api/demo"):
            body = json.dumps({"ok": True, "msg": "from-real"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/files/report.csv"):
            body = b"col1,col2\n1,2\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="report.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt: str, *args) -> None:  # 安静模式
        pass


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
