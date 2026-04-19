"""Generate a password hash for use in TIMELINE_PASSWORD env var."""
from getpass import getpass
from werkzeug.security import generate_password_hash

password = getpass("Enter your password: ")
confirm = getpass("Confirm password: ")

if password != confirm:
    print("Passwords don't match!")
    exit(1)

hash_value = generate_password_hash(password)
print(f"\nYour password hash:\n{hash_value}")
print("\nCopy this hash — it will be used by the setup script.")
