"""Start the backend as a fully detached process.

Why not `start /b` in the .bat: the launcher cmd has stdout redirected to
logs/launcher.log, and a `start /b` child inherits that handle, locking
launcher.log for the server's whole lifetime. Every later launch then fails
silently at the redirect. Spawning via subprocess with close_fds=True breaks
the handle-inheritance chain; DETACHED_PROCESS also frees the server from the
launcher's hidden console.
"""
import os
import subprocess
import sys


def main() -> int:
    port = sys.argv[1]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend = os.path.join(root, "backend")
    log_path = os.path.join(root, "logs", f"backend-{port}.log")
    # pythonw.exe never allocates a console: uvicorn's --workers spawn would
    # otherwise pop a visible terminal window for the child process.
    python = os.path.join(backend, ".venv", "Scripts", "pythonw.exe")
    if not os.path.exists(python):
        python = os.path.join(backend, ".venv", "Scripts", "python.exe")
    with open(log_path, "ab") as log:
        subprocess.Popen(
            [
                python, "-m", "uvicorn", "main:app",
                "--host", "127.0.0.1", "--port", port,
                "--workers", "1", "--no-access-log",
            ],
            cwd=backend,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
