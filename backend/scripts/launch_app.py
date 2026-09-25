"""Start the local presentation server and open it in a browser."""

import threading
import time
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn


APP_URL = "http://127.0.0.1:8000/"


def open_browser_when_ready() -> None:
    for _ in range(40):
        try:
            with urlopen(APP_URL, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(APP_URL)
                    return
        except (OSError, URLError):
            time.sleep(0.25)


def main() -> None:
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
