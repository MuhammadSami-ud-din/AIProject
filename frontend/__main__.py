"""Allow running the game with: uv run python -m frontend"""
from frontend.main import main

# The guard matters: the background trainer uses multiprocessing "spawn",
# which re-imports this module in the child process (as __mp_main__).
if __name__ == "__main__":
    main()
