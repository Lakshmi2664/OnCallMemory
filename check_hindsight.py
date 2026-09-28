import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()
url = os.getenv("HINDSIGHT_BASE_URL")
key = os.getenv("HINDSIGHT_API_KEY")
print("URL:", url)
print("KEY set:", bool(key), "| length:", len(key) if key else 0)

client = Hindsight(base_url=url, api_key=key, timeout=60.0)
bank = "acme-platform-team"

try:
    client.create_bank(bank_id=bank, name="Acme Platform Team")
    print("create_bank OK")
except Exception as e:
    print("create_bank error:", repr(e))

try:
    client.retain(bank_id=bank, content="test: checkout-service Redis pool exhaustion fixed by raising maxIdle")
    print("retain OK")
except Exception as e:
    print("retain error:", repr(e))

try:
    r = client.recall(bank_id=bank, query="redis connection pool")
    print("recall OK:", [x.text for x in r.results])
except Exception as e:
    print("recall error:", repr(e))