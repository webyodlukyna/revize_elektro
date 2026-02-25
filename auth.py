"""
auth.py – Přihlašování do aplikace (jedno globální heslo)
==========================================================
Heslo je uloženo jako bcrypt hash – nikdy plain text.

Nastavení hesla:
  python auth.py               # interaktivně vygeneruje hash
  python auth.py "MojeHeslo"   # z příkazové řádky

Streamlit Secrets (cloud):
  [auth]
  password_hash = "$2b$12$..."
"""

import sys
import json
from pathlib import Path

import bcrypt

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False

AUTH_CFG = Path("auth_config.json")


# ─── Hash / ověření ───────────────────────────────────────────────────────────

def hashuj_heslo(heslo: str) -> str:
    """Vrátí bcrypt hash hesla (bezpečné uložení)."""
    return bcrypt.hashpw(heslo.encode(), bcrypt.gensalt(rounds=12)).decode()


def over_heslo(heslo: str, ulozeny_hash: str) -> bool:
    """Ověří heslo vůči uloženému hash."""
    try:
        return bcrypt.checkpw(heslo.encode(), ulozeny_hash.encode())
    except Exception:
        return False


# ─── Načtení hashe ────────────────────────────────────────────────────────────

def _nacti_hash() -> str | None:
    """
    Načte hash hesla:
      1. Ze Streamlit Secrets (cloud)
      2. Z auth_config.json (lokálně)
    """
    # Streamlit Cloud
    try:
        return st.secrets["auth"]["password_hash"]
    except Exception:
        pass

    # Lokální soubor
    if AUTH_CFG.exists():
        data = json.loads(AUTH_CFG.read_text(encoding="utf-8"))
        return data.get("password_hash")

    return None


def uloz_hash(password_hash: str) -> None:
    """Uloží hash hesla do auth_config.json."""
    AUTH_CFG.write_text(
        json.dumps({"password_hash": password_hash}, indent=2),
        encoding="utf-8",
    )


# ─── Streamlit přihlašovací obrazovka ─────────────────────────────────────────

def vyzaduj_prihlaseni() -> None:
    """
    Zobrazí přihlašovací obrazovku pokud uživatel není přihlášen.
    Pokud heslo není nastaveno, zobrazí výzvu k nastavení.
    Blokuje zbytek aplikace dokud není přihlášeno.
    """
    if not _HAS_STREAMLIT:
        return  # CLI režim – přeskočit
    if st.session_state.get("prihlaseno"):
        return  # Již přihlášen — pokračuj normálně

    hash_ = _nacti_hash()

    st.markdown("""
    <style>
      .login-box {
        max-width: 420px;
        margin: 80px auto 0;
        background: #1a1d27;
        border: 1px solid #2a2d3e;
        border-radius: 12px;
        padding: 40px 36px;
      }
      .login-title {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.6rem;
        font-weight: 600;
        color: #e0e0e0;
        margin-bottom: 6px;
      }
      .login-sub {
        color: #888;
        font-size: 0.9rem;
        margin-bottom: 28px;
      }
    </style>
    <div class="login-box">
      <div class="login-title">⚡ Elektro revize</div>
      <div class="login-sub">Přihlaste se pro přístup do aplikace</div>
    </div>
    """, unsafe_allow_html=True)

    # Heslo ještě není nastaveno
    if hash_ is None:
        st.warning("⚠️ Heslo aplikace není nastaveno.")
        st.markdown("Spusťte v terminálu:")
        st.code("python auth.py", language="bash")
        st.markdown("nebo nastavte `[auth] password_hash` ve Streamlit Secrets.")
        st.stop()

    # Přihlašovací formulář
    with st.form("login_form"):
        heslo = st.text_input("Heslo", type="password", placeholder="Zadejte heslo")
        ok    = st.form_submit_button("🔓 Přihlásit se", use_container_width=True)

    if ok:
        if over_heslo(heslo, hash_):
            st.session_state["prihlaseno"] = True
            st.rerun()
        else:
            st.error("❌ Nesprávné heslo.")

    st.stop()  # Zbytek aplikace se nevykreslí dokud není přihlášeno


# ─── CLI – nastavení hesla ────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        heslo = sys.argv[1]
    else:
        import getpass
        heslo  = getpass.getpass("Zadejte nové heslo aplikace: ")
        heslo2 = getpass.getpass("Zopakujte heslo: ")
        if heslo != heslo2:
            print("❌ Hesla se neshodují.")
            sys.exit(1)

    h = hashuj_heslo(heslo)
    uloz_hash(h)
    print(f"✅ Heslo nastaveno a uloženo do {AUTH_CFG}")
    print(f"\nPro Streamlit Secrets přidejte:")
    print(f'[auth]\npassword_hash = "{h}"')
