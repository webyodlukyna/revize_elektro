"""
config.py – Správa konfigurace a odesílání e-mailů
"""

import json
import os
import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CFG_PATH = "revize_config.json"


def nacti_config() -> dict:
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def uloz_config(cfg: dict) -> None:
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def config_ok(cfg: dict) -> bool:
    """Vrátí True, pokud je konfigurace kompletní."""
    return bool(cfg.get("smtp_user") and cfg.get("smtp_pass") and cfg.get("prijemci"))


# ─── E-mail ───────────────────────────────────────────────────────────────────

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
        <h1 style='margin:0'>⚡ Hlídání elektro revizí</h1>
        <p style='margin:5px 0 0'>{dnes.strftime('%d.%m.%Y')}</p>
      </div>
      <div style='padding:20px;border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px'>
        {sekce_prosle}
        {sekce_blizici}
        <p style='color:#7f8c8d;font-size:12px;margin-top:30px'>
          Automatické upozornění – systém hlídání elektro revizí
        </p>
      </div>
    </body></html>"""


def odeslat_email(cfg: dict, rows: list[dict]) -> None:
    """
    Sestaví a odešle HTML e-mail s přehledem revizí.
    Vyvolá výjimku při chybě (ošetřete na straně volajícího).
    """
    dnes  = date.today()
    html  = _sestavit_html(rows, dnes)

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ Upozornění na elektro revize – {dnes.strftime('%d.%m.%Y')}"
    msg["From"]    = cfg["smtp_user"]
    msg["To"]      = ", ".join(cfg["prijemci"])
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"])) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["smtp_user"], cfg["smtp_pass"])
        server.sendmail(cfg["smtp_user"], cfg["prijemci"], msg.as_string())
