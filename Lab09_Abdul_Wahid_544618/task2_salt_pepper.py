from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "users.json"
DEFAULT_ENV_PATH = BASE_DIR / ".env"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

PEPPER_HELP = """Error: PASSWORD_PEPPER is not set.
Set it in your terminal or create a local .env file before running Task 2.

Windows PowerShell:
  $env:PASSWORD_PEPPER = "your-random-secret-pepper"

Linux / macOS:
  export PASSWORD_PEPPER="your-random-secret-pepper"
"""


def validate_username(username):
    """Strip and check that the username uses allowed characters."""
    cleaned = username.strip()
    if not cleaned:
        raise ValueError("Username cannot be empty.")
    if not USERNAME_RE.match(cleaned):
        raise ValueError(
            "Invalid username. Use 1 to 64 characters (letters, digits, _, ., -)."
        )
    return cleaned


def _read_env_file(env_path=DEFAULT_ENV_PATH):
    """Tiny parser for KEY=VALUE lines in a local .env file."""
    values = {}
    candidates = [Path(".env"), Path(env_path)]
    for path in candidates:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            values[key] = val
        break
    return values


def get_pepper(env_path=DEFAULT_ENV_PATH):
    """Load the secret pepper from PASSWORD_PEPPER or fall back to .env."""
    pepper = os.environ.get("PASSWORD_PEPPER", "").strip()
    if not pepper:
        pepper = _read_env_file(env_path).get("PASSWORD_PEPPER", "").strip()
    if not pepper:
        raise RuntimeError(PEPPER_HELP.strip())
    return pepper


def hash_password(password, salt, pepper=None):
    """Compute SHA-512(salt + password_bytes + pepper) as a hex string."""
    if not password:
        raise ValueError("Password cannot be empty.")
    if pepper is None:
        pepper = get_pepper()

    salt_bytes = bytes.fromhex(salt) if isinstance(salt, str) else bytes(salt)
    password_bytes = (
        password.encode("utf-8") if isinstance(password, str) else bytes(password)
    )
    pepper_bytes = (
        pepper.encode("utf-8") if isinstance(pepper, str) else bytes(pepper)
    )

    # manual specifies combining salt + password + pepper in this exact order
    combined = salt_bytes + password_bytes + pepper_bytes
    return hashlib.sha512(combined).hexdigest()


# Bonus (optional): key-stretching version with PBKDF2-HMAC-SHA512.
# Kept separate so the main program still follows the lab manual's plain SHA-512 requirement.
def hash_password_pbkdf2(password, salt, pepper=None, iterations=600_000):
    """Bonus: slow password hashing using PBKDF2-HMAC-SHA512 (600,000 rounds)."""
    if not password:
        raise ValueError("Password cannot be empty.")
    if pepper is None:
        pepper = get_pepper()

    salt_bytes = bytes.fromhex(salt) if isinstance(salt, str) else bytes(salt)
    password_bytes = (
        password.encode("utf-8") if isinstance(password, str) else bytes(password)
    )
    pepper_bytes = (
        pepper.encode("utf-8") if isinstance(pepper, str) else bytes(pepper)
    )

    derived = hashlib.pbkdf2_hmac(
        "sha512", password_bytes + pepper_bytes, salt_bytes, iterations
    )
    return derived.hex()


def load_db(db_path=DEFAULT_DB_PATH):
    """Read the user database JSON, returning an empty dict if missing."""
    path = Path(db_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Error: '{path.name}' is corrupted and could not be parsed as JSON.")
        return {}

    if not isinstance(data, dict):
        print(f"Error: '{path.name}' does not contain a valid JSON object.")
        return {}
    return data


def save_db(db, db_path=DEFAULT_DB_PATH):
    """Atomically write the user database via a .tmp file."""
    path = Path(db_path)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(db, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows doesn't support POSIX 0600 permissions the same way
        pass


def register_user(username, password, db_path=DEFAULT_DB_PATH, pepper=None):
    """Register a new user with a random 16-byte salt and SHA-512 hash."""
    cleaned_user = validate_username(username)
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    db = load_db(db_path)
    if cleaned_user in db:
        raise ValueError(f"User '{cleaned_user}' already exists.")

    salt = secrets.token_bytes(16)
    digest = hash_password(password, salt, pepper=pepper)

    record = {
        "algorithm": "SHA-512",
        "salt": salt.hex(),
        "hash": digest,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    db[cleaned_user] = record
    save_db(db, db_path)
    return record


def verify_user(username, password, db_path=DEFAULT_DB_PATH, pepper=None):
    """Check a username and password against the stored salt and hash."""
    cleaned_user = username.strip()
    if not cleaned_user or not password:
        return False

    db = load_db(db_path)
    record = db.get(cleaned_user)
    if not isinstance(record, dict):
        return False

    salt_hex = record.get("salt", "")
    stored_hash = record.get("hash", "")
    if not isinstance(salt_hex, str) or not isinstance(stored_hash, str):
        return False

    try:
        salt = bytes.fromhex(salt_hex)
        if not salt:
            return False
        candidate_hash = hash_password(password, salt, pepper=pepper)
    except (ValueError, RuntimeError):
        return False

    # constant-time comparison so timing doesn't leak partial hash matches
    return hmac.compare_digest(candidate_hash, stored_hash)


def _handle_register(db_path):
    raw_user = input("Username: ")
    try:
        username = validate_username(raw_user)
    except ValueError as err:
        print(f"Error: {err}")
        return

    db = load_db(db_path)
    if username in db:
        print(f"Error: User '{username}' already exists.")
        return

    while True:
        password = getpass.getpass("Password (min 8 chars): ")
        if len(password) < 8:
            print("Error: Password must be at least 8 characters long.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Please try again.")
            continue
        break

    try:
        register_user(username, password, db_path=db_path)
        print(f"User '{username}' registered successfully.")
    except ValueError as err:
        print(f"Error: {err}")


def _handle_login(db_path):
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    if verify_user(username, password, db_path=db_path):
        print(f"Login successful. Welcome, {username}.")
    else:
        print("Login failed.")


def _handle_view_db(db_path):
    db = load_db(db_path)
    if not db:
        print("Database is currently empty ({}).")
    else:
        print(json.dumps(db, indent=2))
    print("Note: The secret pepper is not stored in users.json.")


def main():
    try:
        get_pepper()
    except RuntimeError as err:
        print(err)
        sys.exit(1)

    print("CS-353 Lab 09 - Task 2: Password Hashing with Salt and Pepper")
    try:
        while True:
            print("\n1) Register  2) Login  3) View database  4) Exit")
            choice = input("Select an option (1-4): ").strip()
            if choice == "1":
                _handle_register(DEFAULT_DB_PATH)
            elif choice == "2":
                _handle_login(DEFAULT_DB_PATH)
            elif choice == "3":
                _handle_view_db(DEFAULT_DB_PATH)
            elif choice == "4":
                print("Goodbye.")
                break
            else:
                print("Invalid option. Please enter 1, 2, 3, or 4.")
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
