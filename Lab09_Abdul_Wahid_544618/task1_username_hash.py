import getpass
import hashlib
import re
import sys

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


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


def make_hash(username, password):
    """Return the SHA-512 hex digest of username and password combined."""
    cleaned_user = validate_username(username)
    if not password:
        raise ValueError("Password cannot be empty.")

    # colon so 'ab'+'c' and 'a'+'bc' don't hash the same
    combined = f"{cleaned_user}:{password}".encode("utf-8")
    return hashlib.sha512(combined).hexdigest()


def main():
    print("CS-353 Lab 09 - Task 1: Username + Password Hashing (SHA-512)")
    try:
        while True:
            print()
            raw_user = input("Enter username: ")
            try:
                username = validate_username(raw_user)
            except ValueError as err:
                print(f"Error: {err}")
                continue

            password = getpass.getpass("Enter password: ")
            if not password:
                print("Error: Password cannot be empty.")
                continue

            digest = make_hash(username, password)
            print(f"Username : {username}")
            print("Algorithm: SHA-512")
            print(f"Hash     : {digest}")

            again = input("\nHash another user? (y/n): ").strip().lower()
            if again != "y":
                break
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
