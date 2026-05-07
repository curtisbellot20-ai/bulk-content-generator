"""Entry point that loads .env before running the app."""
import load_env  # noqa: F401 — must be first to set env vars
import app

if __name__ == "__main__":
    app.main()
