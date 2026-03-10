# vytvořil lukyn.sifty@gmail.com copyright 2025
"""
config.py – Správa konfigurace a odesílání e-mailů
===================================================
Bezpečnost:
  - Lokálně: heslo zašifrováno pomocí Fernet (symetrická šifra AES-128)
             klíč uložen v separátním souboru .secret.key
  - Cloud:   načítá ze Streamlit Secrets (st.secrets), JSON soubor se vůbec nepoužívá

Streamlit Secrets (pro nasazení na share.streamlit.io):
  V dashboardu přidejte sekci [email]:
    [email]
    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    smtp_user = "vas@email.cz"
    smtp_pass = "app-password"
    prijemci  = ["prijemce1@email.cz", "prijemce2@email.cz"]
"""

import json
import os
import smtplib
import urllib.request
import urllib.error
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from cryptography.fernet import Fernet

# ─── Cesty ────────────────────────────────────────────────────────────────────
CFG_PATH = Path("revize_config.json")
KEY_PATH = Path(".secret.key")   # skrytý soubor, NIKDY nedávat do Gitu


# ─── Detekce prostředí ────────────────────────────────────────────────────────

def _je_streamlit_cloud() -> bool:
    """Vrátí True pokud běžíme na Streamlit Cloud a secrets jsou k dispozici."""
    try:
        import streamlit as st
        _ = st.secrets["email"]["smtp_user"]
        return True
    except Exception:
        return False


# ─── Správa šifrovacího klíče ─────────────────────────────────────────────────

def _nacti_nebo_vygeneruj_klic() -> Fernet:
    """Načte existující klíč nebo vygeneruje nový a uloží ho."""
    if KEY_PATH.exists():
        key = KEY_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_PATH.write_bytes(key)
        # Skryjeme soubor na Windows
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(KEY_PATH), 2)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            pass
        print(f"[config] Vygenerován nový šifrovací klíč: {KEY_PATH}")
    return Fernet(key)


def _sifrovani() -> Fernet:
    return _nacti_nebo_vygeneruj_klic()


# ─── Načtení konfigurace ──────────────────────────────────────────────────────

def nacti_config() -> dict:
    """
    Načte konfiguraci:
      - Z Streamlit Secrets (pokud běží na cloudu)
      - Ze zašifrovaného JSON souboru (lokálně)
    Vrátí dict s klíči: smtp_host, smtp_port, smtp_user, smtp_pass, prijemci
    """
    if _je_streamlit_cloud():
        import streamlit as st
        s = st.secrets["email"]
        return {
            "smtp_host": s["smtp_host"],
            "smtp_port": int(s["smtp_port"]),
            "smtp_user": s["smtp_user"],
            "smtp_pass": s["smtp_pass"],
            "prijemci":  list(s["prijemci"]),
            "webhook_url": s.get("webhook_url", ""),
        }

    if not CFG_PATH.exists():
        return {}

    raw = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    fernet = _sifrovani()

    # Dešifrujeme heslo (zpětná kompatibilita: pokud ještě není zašifrováno)
    smtp_pass = raw.get("smtp_pass", "")
    if smtp_pass.startswith("enc:"):
        try:
            smtp_pass = fernet.decrypt(smtp_pass[4:].encode()).decode()
        except Exception:
            smtp_pass = ""

    return {
        "smtp_host": raw.get("smtp_host", "smtp.gmail.com"),
        "smtp_port": int(raw.get("smtp_port", 587)),
        "smtp_user": raw.get("smtp_user", ""),
        "smtp_pass": smtp_pass,
        "prijemci":  raw.get("prijemci", []),
        "webhook_url": raw.get("webhook_url", ""),
    }


# ─── Uložení konfigurace ──────────────────────────────────────────────────────

def uloz_config(cfg: dict) -> None:
    """
    Uloží konfiguraci lokálně.
    Heslo je zašifrováno Fernetem před zápisem do JSON.
    Na Streamlit Cloud se nepoužívá — konfigurace je v Secrets.
    """
    fernet    = _sifrovani()
    encrypted = "enc:" + fernet.encrypt(cfg["smtp_pass"].encode()).decode()

    data = {
        "smtp_host": cfg["smtp_host"],
        "smtp_port": int(cfg["smtp_port"]),
        "smtp_user": cfg["smtp_user"],
        "smtp_pass": encrypted,          # nikdy plain text
        "prijemci":  cfg["prijemci"],
        "webhook_url": cfg.get("webhook_url", ""),
    }
    CFG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Validace ─────────────────────────────────────────────────────────────────

def config_ok(cfg: dict) -> bool:
    """Vrátí True, pokud je konfigurace kompletní pro odesílání."""
    return bool(
        cfg.get("smtp_host")
        and cfg.get("smtp_user")
        and cfg.get("smtp_pass")
        and cfg.get("prijemci")
    )


def webhook_ok(cfg: dict) -> bool:
    return bool((cfg.get("webhook_url") or "").strip())


def _smtp_auth_data(cfg: dict) -> tuple[str, str, str, int]:
    """Vrátí normalizované SMTP přihlašovací údaje."""
    host = str(cfg.get("smtp_host") or "").strip()
    user = str(cfg.get("smtp_user") or "").strip()
    pwd = str(cfg.get("smtp_pass") or "").strip()
    port = int(cfg.get("smtp_port", 587))

    # Google App Password se často kopíruje ve skupinách oddělených mezerou.
    if "gmail.com" in host.lower() and " " in pwd:
        pwd = pwd.replace(" ", "")

    return host, user, pwd, port


def otestovat_smtp(cfg: dict, timeout_sec: int = 20) -> tuple[bool, str]:
    """
    Ověří SMTP připojení a přihlášení bez odeslání e-mailu.
    Vrací (ok, zpráva).
    """
    host, user, pwd, port = _smtp_auth_data(cfg)
    try:
        port = int(port)
    except Exception:
        return False, "Neplatný SMTP port."

    if not host or not user or not pwd:
        return False, "Chybí SMTP server, e-mail nebo heslo/app password."

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout_sec) as server:
                server.ehlo()
                server.login(user, pwd)
        else:
            with smtplib.SMTP(host, port, timeout=timeout_sec) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(user, pwd)
        return True, "SMTP připojení i přihlášení proběhlo úspěšně."
    except smtplib.SMTPAuthenticationError as exc:
        detail = ""
        try:
            detail = exc.smtp_error.decode(errors="ignore") if isinstance(exc.smtp_error, (bytes, bytearray)) else str(exc.smtp_error)
        except Exception:
            detail = ""
        code = getattr(exc, "smtp_code", "")
        suffix = f" (kód {code})" if code else ""
        if detail:
            return False, f"SMTP autentizace selhala{suffix}: {detail}"
        return False, f"SMTP autentizace selhala{suffix}. Zkontrolujte e-mail a App Password."
    except TimeoutError:
        return False, "SMTP timeout. Ověřte host/port; obvykle 587 (STARTTLS) nebo 465 (SSL)."
    except smtplib.SMTPException as exc:
        return False, f"SMTP chyba: {exc}"
    except OSError as exc:
        return False, f"Síťová chyba při připojení na SMTP: {exc}"


# ─── Sestavení HTML e-mailu ───────────────────────────────────────────────────

def _fmt_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y") if d else "—"


def _sestavit_html(rows: list[dict], dnes: date) -> str:
    prosle  = [r for r in rows if datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() < dnes]
    blizici = [r for r in rows if datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() >= dnes]

    def trow(r: dict) -> str:
        plat  = datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date()
        zb    = (plat - dnes).days
        barva = "#c0392b" if zb < 0 else "#e67e22"
        stav  = f"PROŠLÁ ({abs(zb)} dní)" if zb < 0 else f"Za {zb} dní"
        return (
            f"<tr>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r['nazev']}</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.get('umisteni') or '—'}</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{r.get('typ') or '—'}</td>"
            f"<td style='padding:8px;border:1px solid #ddd'>{_fmt_date(r['datum_platnosti'])}</td>"
            f"<td style='padding:8px;border:1px solid #ddd;color:{barva};font-weight:bold'>{stav}</td>"
            f"</tr>"
        )

    hlavicka = (
        "<table style='border-collapse:collapse;width:100%'>"
        "<tr style='background:#2c3e50;color:white'>"
        "<th style='padding:10px;border:1px solid #ddd;text-align:left'>Zařízení</th>"
        "<th style='padding:10px;border:1px solid #ddd;text-align:left'>Umístění</th>"
        "<th style='padding:10px;border:1px solid #ddd;text-align:left'>Typ</th>"
        "<th style='padding:10px;border:1px solid #ddd;text-align:left'>Platnost</th>"
        "<th style='padding:10px;border:1px solid #ddd;text-align:left'>Stav</th>"
        "</tr>"
    )

    sekce_prosle = (
        f"<h2 style='color:#c0392b'>❌ Prošlé revize</h2>"
        f"{hlavicka}{''.join(trow(r) for r in prosle)}</table>"
    ) if prosle else ""

    sekce_blizici = (
        f"<h2 style='color:#e67e22'>⚠️ Blížící se expirace</h2>"
        f"{hlavicka}{''.join(trow(r) for r in blizici)}</table>"
    ) if blizici else ""

    return f"""
    <html><body style='font-family:Arial,sans-serif;max-width:800px;margin:auto;padding:20px'>
      <div style='background:#2c3e50;color:white;padding:20px;border-radius:6px 6px 0 0'>
        <h1 style='margin:0'>⚡ RP ELECTRIC SOLUTION s.r.o.</h1>
        <p style='margin:5px 0 0'>{dnes.strftime('%d.%m.%Y')}</p>
      </div>
      <div style='padding:20px;border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px'>
        {sekce_prosle}
        {sekce_blizici}
        <p style='color:#7f8c8d;font-size:12px;margin-top:30px'>
                    Automatické upozornění – RP ELECTRIC SOLUTION s.r.o.
        </p>
      </div>
    </body></html>"""


# ─── Odesílání e-mailu ────────────────────────────────────────────────────────

def odeslat_email(cfg: dict, rows: list[dict]) -> None:
    """
    Sestaví a odešle HTML e-mail s přehledem revizí.
    Vyvolá výjimku při chybě — ošetřete na straně volajícího.
    """
    dnes = date.today()
    html = _sestavit_html(rows, dnes)

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ Upozornění na RP ELECTRIC SOLUTION s.r.o. – {dnes.strftime('%d.%m.%Y')}"
    msg["From"]    = cfg["smtp_user"]
    msg["To"]      = ", ".join(cfg["prijemci"])
    msg.attach(MIMEText(html, "html", "utf-8"))

    host, user, pwd, port = _smtp_auth_data(cfg)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.ehlo()
            server.login(user, pwd)
            server.sendmail(user, cfg["prijemci"], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, pwd)
            server.sendmail(user, cfg["prijemci"], msg.as_string())


def odeslat_webhook(cfg: dict, rows: list[dict]) -> None:
    """
    Odešle upozornění přes webhook (JSON POST).
    Vhodné pro SMS brány, Teams, Slack, Make/Zapier apod.
    """
    webhook_url = (cfg.get("webhook_url") or "").strip()
    if not webhook_url:
        raise ValueError("Webhook URL není nastaveno.")

    dnes = date.today()
    payload = {
        "source": "RP ELECTRIC SOLUTION s.r.o.",
        "generated_at": dnes.strftime("%Y-%m-%d"),
        "count": len(rows),
        "items": [
            {
                "id": r.get("id"),
                "nazev": r.get("nazev"),
                "umisteni": r.get("umisteni"),
                "typ": r.get("typ"),
                "datum_platnosti": r.get("datum_platnosti"),
                "revizni_technik": r.get("revizni_technik"),
            }
            for r in rows
        ],
    }

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = getattr(resp, "status", 200)
            if code >= 400:
                raise RuntimeError(f"Webhook vrátil HTTP {code}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Webhook odeslání selhalo: {exc}") from exc
