"""
WSGI 入口 — 生产环境使用 waitress (Windows) 或 gunicorn (Linux)
  Linux:   gunicorn wsgi:app -w 4 -b 0.0.0.0:5000
  Windows: python wsgi.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

if __name__ == "__main__":
    import platform
    if platform.system() == "Windows":
        from waitress import serve
        port = int(os.environ.get("PORT", 5000))
        threads = int(os.environ.get("WORKER_THREADS", 4))
        print(f"[WSGI] waitress on 0.0.0.0:{port} (threads={threads})")
        serve(app, host="0.0.0.0", port=port, threads=threads)
    else:
        # Fallback to Flask dev server (production should use gunicorn)
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
