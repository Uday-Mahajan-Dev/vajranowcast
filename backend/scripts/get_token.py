import getpass
import httpx
from pathlib import Path

# Read backend/.env without extra packages
env = {}
for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

url = env.get("SUPABASE_URL")
anon = env.get("SUPABASE_ANON_KEY") or env.get("SUPABASE_KEY") or env.get("SUPABASE_PUBLISHABLE_KEY")
if not url or not anon:
    raise SystemExit(f"Missing SUPABASE_URL or anon key in .env. Keys found: {list(env)}")

email = input("Email: ")
password = getpass.getpass("Password (hidden): ")

r = httpx.post(f"{url}/auth/v1/token?grant_type=password",
               headers={"apikey": anon}, json={"email": email, "password": password})
if r.status_code != 200:
    raise SystemExit(f"Login failed ({r.status_code}): {r.text}")

data = r.json()
print("\nRole:", data["user"].get("app_metadata", {}).get("role"))
print("\nAccess token (valid ~1 hour):\n")
print(data["access_token"])