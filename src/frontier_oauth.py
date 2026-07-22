"""
Frontier Companion API (cAPI) login — the OAuth2 flow Inara/EDMC use to import
commander data straight from Frontier's servers.

This is the "official" login. It speaks OAuth2 with PKCE against
auth.frontierstore.net and then reads the commander profile from
companion.orerve.net.

IMPORTANT — you need a client_id:
    Frontier issues OAuth client_ids only to approved developers
    (https://user.frontierstore.net/developer/). The redirect URI you register
    must match REDIRECT_URI below. Without an approved client_id this flow
    cannot complete — that is a Frontier restriction, not a bug here. Paste your
    client_id in the app's Settings (Advanced) to enable the "Connect with
    Frontier" button. Until then the app uses the Inara/EDSM key hooks instead.

Standard library only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

AUTH_URL = "https://auth.frontierstore.net/auth"
TOKEN_URL = "https://auth.frontierstore.net/token"
PROFILE_URL = "https://companion.orerve.net/profile"
SCOPE = "auth capi"

# Must exactly match the redirect URI registered with your Frontier client_id.
REDIRECT_PATH = "/oauth/callback"


def redirect_uri(host: str, port: int) -> str:
    return f"http://{host}:{port}{REDIRECT_PATH}"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def begin(client_id: str, host: str, port: int) -> dict:
    """
    Build the authorization URL + the transient state/verifier to stash.
    Returns {authUrl, state, verifier}.
    """
    verifier = _b64url(os.urandom(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri(host, port),
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {
        "authUrl": AUTH_URL + "?" + urllib.parse.urlencode(params),
        "state": state,
        "verifier": verifier,
    }


def exchange_code(client_id: str, code: str, verifier: str,
                  host: str, port: int) -> dict:
    """Swap an authorization code for an access token."""
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri(host, port),
    }).encode("ascii")
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Token exchange failed (HTTP {e.code}): {body}") from None


def fetch_profile(access_token: str) -> dict:
    """Read the live commander profile from the Companion API."""
    req = urllib.request.Request(PROFILE_URL)
    req.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Companion profile fetch failed (HTTP {e.code}).") from None


def normalise_profile(raw: dict) -> dict:
    """Reduce the large cAPI profile blob to the fields the UI shows."""
    cmdr = raw.get("commander", {}) or {}
    ship = raw.get("ship", {}) or {}
    rank = cmdr.get("rank", {}) or {}
    return {
        "commanderName": cmdr.get("name"),
        "credits": cmdr.get("credits"),
        "combatRank": rank.get("combat"),
        "tradeRank": rank.get("trade"),
        "exploreRank": rank.get("explore"),
        "mainShip": ship.get("name") or (ship.get("shipName") if ship else None),
        "system": (raw.get("lastSystem", {}) or {}).get("name"),
        "source": "frontier",
    }
