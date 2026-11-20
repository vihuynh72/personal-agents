"""One live call per external service. Run: set -a && . ./.env && set +a && uv run python scripts/check_connectors.py
Prints OK/FAIL/SKIP per service. Never prints a key."""
import base64
import json
import os
import urllib.error
import urllib.request

E = os.environ.get


def call(url, headers=None, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"content-type": "application/json", "user-agent": "connector-check", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode(errors="replace")


def anthropic():
    call("https://api.anthropic.com/v1/models", {"x-api-key": E("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})


def gemini():
    call(f"https://generativelanguage.googleapis.com/v1beta/models/{E('GEMINI_MODEL')}", {"x-goog-api-key": E("GEMINI_API_KEY")})


def stripe():
    key = E("STRIPE_SECRET_KEY")
    assert "_test_" in key, "not a test key"
    call("https://api.stripe.com/v1/balance", {"authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()})


def brightdata():
    out = call("https://api.brightdata.com/request", {"authorization": f"Bearer {E('BRIGHTDATA_API_KEY')}"},
               {"zone": E("BRIGHTDATA_UNLOCKER_ZONE"), "url": "https://www.walmart.com/search?q=ground+coffee", "format": "raw"})
    assert "coffee" in out.lower(), "page fetched but no product text in it"


def cognee():
    call(E("COGNEE_URL").rstrip("/") + "/api/v1/datasets", {"x-api-key": E("COGNEE_API_KEY")})


def airbyte():
    out = call("https://api.airbyte.com/v1/applications/token", body={
        "client_id": E("AIRBYTE_CLIENT_ID"), "client_secret": E("AIRBYTE_CLIENT_SECRET"), "grant-type": "client_credentials"})
    assert "access_token" in out


def elevenlabs():
    call("https://api.elevenlabs.io/v1/voices/" + E("ELEVENLABS_VOICE_ID"), {"xi-api-key": E("ELEVENLABS_API_KEY")})


def railway():
    assert '"ok":true' in call("https://personal-agents-production-81468651.up.railway.app/health").replace(" ", "")


CHECKS = {
    "Claude (System 2)": (anthropic, ["ANTHROPIC_API_KEY"]),
    "Gemini (System 1)": (gemini, ["GEMINI_API_KEY", "GEMINI_MODEL"]),
    "Stripe test mode": (stripe, ["STRIPE_SECRET_KEY"]),
    "Bright Data product pull": (brightdata, ["BRIGHTDATA_API_KEY", "BRIGHTDATA_UNLOCKER_ZONE"]),
    "Cognee memory": (cognee, ["COGNEE_URL", "COGNEE_API_KEY"]),
    "Airbyte": (airbyte, ["AIRBYTE_CLIENT_ID", "AIRBYTE_CLIENT_SECRET"]),
    "ElevenLabs voice": (elevenlabs, ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"]),
    "Railway API": (railway, []),
    "Photon iMessage": (None, ["PHOTON_PROJECT_ID", "PHOTON_PROJECT_SECRET"]),
    "Persona": (None, ["PERSONA_API_KEY"]),
    "Senso": (None, ["SENSO_API_KEY"]),
    "Guild AI": (None, ["GUILD_API_KEY"]),
    "Firedrill": (None, ["FIREDRILL_API_KEY"]),
}

if __name__ == "__main__":
    for name, (fn, needs) in CHECKS.items():
        missing = [n for n in needs if not E(n)]
        if missing:
            print(f"SKIP  {name}: missing {', '.join(missing)}")
        elif fn is None:
            print(f"SKIP  {name}: no check written yet")
        else:
            try:
                fn()
                print(f"OK    {name}")
            except urllib.error.HTTPError as e:
                print(f"FAIL  {name}: HTTP {e.code} {e.read().decode(errors='replace')[:120]!r}")
            except Exception as e:
                print(f"FAIL  {name}: {type(e).__name__} {str(e)[:120]}")
