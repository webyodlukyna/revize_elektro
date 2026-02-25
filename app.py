"""
Hlídání elektro revizí – Streamlit webová aplikace
===================================================
Spuštění:
  pip install streamlit
  streamlit run app.py

Nasazení (zdarma):
  https://streamlit.io/cloud  → připojte GitHub repozitář
"""

import streamlit as st
import sqlite3
import smtplib
import json
import os
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─── Konfigurace stránky ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Elektro revize",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
  h1, h2, h3 { font-family: 'IBM Plex Mono', monospace !important; }

  .stApp { background-color: #0f1117; color: #e0e0e0; }

  .metric-card {
    background: #1a1d27;
    border: 1px solid #2a2d3e;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
  }
  .metric-card .number { font-size: 2.5rem; font-weight: 600; font-family: 'IBM Plex Mono', monospace; }
  .metric-card .label  { font-size: 0.85rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }

  .red    { color: #e74c3c !important; }
  .orange { color: #e67e22 !important; }
  .green  { color: #2ecc71 !important; }
  .yellow { color: #f1c40f !important; }

  .revize-row {
    background: #1a1d27;
    border: 1px solid #2a2d3e;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .status-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 600;
    font-family: 'IBM Plex Mono', monospace;
  }
  .badge-red    { background: #3d1a1a; color: #e74c3c; border: 1px solid #e74c3c44; }
  .badge-orange { background: #3d2a1a; color: #e67e22; border: 1px solid #e67e2244; }
  .badge-green  { background: #1a3d2a; color: #2ecc71; border: 1px solid #2ecc7144; }

  div[data-testid="stSidebar"] {
    background: #13151f;
    border-right: 1px solid #2a2d3e;
  }

  .stButton > button {
    background: #1a1d27;
    color: #e0e0e0;
    border: 1px solid #3a3d4e;
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    transition: all 0.2s;
  }
  .stButton > button:hover {
    background: #252839;
    border-color: #5a8dee;
    color: #5a8dee;
  }

  .stTextInput > div > div > input,
  .stSelectbox > div > div,
  .stDateInput > div > div > input,
  .stTextArea textarea {
    background: #1a1d27 !important;
    border: 1px solid #2a2d3e !important;
    color: #e0e0e0 !important;
    border-radius: 6px !important;
  }

  .header-bar {
    background: linear-gradient(135deg, #1a1d27 0%, #13151f 100%);
    border: 1px solid #2a2d3e;
    border-radius: 10px;
    padding: 24px 28px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  hr { border-color: #2a2d3e !important; }
</style>
""", unsafe_allow_html=True)

# ─── Databáze ─────────────────────────────────────────────────────────────────
DB_PATH  = "revize_elektro.db"
CFG_PATH = "revize_config.json"

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS revize (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nazev TEXT NOT NULL,
            umisteni TEXT,
            typ TEXT,
            datum_revize TEXT NOT NULL,
            datum_platnosti TEXT NOT NULL,
            revizni_technik TEXT,
            poznamka TEXT,
            upozorneni_odeslano INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()

def get_all():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM revize ORDER BY datum_platnosti").fetchall()
    con.close()
    return [dict(r) for r in rows]

def pridat(data):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO revize (nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka)
        VALUES (:nazev,:umisteni,:typ,:datum_revize,:datum_platnosti,:revizni_technik,:poznamka)
    """, data)
    con.commit()
    con.close()

def smazat(rid):
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM revize WHERE id=?", (rid,))
    con.commit()
    con.close()

def oznacit_odeslano(ids):
    con = sqlite3.connect(DB_PATH)
    con.execute(f"UPDATE revize SET upozorneni_odeslano=1 WHERE id IN ({','.join('?'*len(ids))})", ids)
    con.commit()
    con.close()

# ─── Konfigurace ──────────────────────────────────────────────────────────────
def nacti_config():
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def uloz_config(cfg):
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def stav(d_plat: str):
    plat  = datetime.strptime(d_plat, "%Y-%m-%d").date()
    zbyvá = (plat - date.today()).days
    if zbyvá < 0:
        return "❌ Prošlá",  "badge-red",    zbyvá
    elif zbyvá <= 7:
        return f"⚠️ Za {zbyvá} dní",  "badge-orange", zbyvá
    elif zbyvá <= 30:
        return f"🔔 Za {zbyvá} dní", "badge-orange", zbyvá
    else:
        return f"✅ Za {zbyvá} dní", "badge-green",  zbyvá

def fmt_date(d):
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y") if d else "—"

# ─── E-mail ───────────────────────────────────────────────────────────────────
def odeslat_email(cfg, rows):
    dnes   = date.today()
    prosle = [r for r in rows if datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() < dnes]
    bliz   = [r for r in rows if datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() >= dnes]

    def trow(r):
        plat  = datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date()
        zb    = (plat - dnes).days
        barva = "#c0392b" if zb < 0 else "#e67e22"
        stav_ = f"PROŠLÁ ({abs(zb)} dní)" if zb < 0 else f"Za {zb} dní"
        return f"<tr><td style='padding:8px;border:1px solid #ddd'>{r['nazev']}</td><td style='padding:8px;border:1px solid #ddd'>{r.get('umisteni') or '—'}</td><td style='padding:8px;border:1px solid #ddd'>{r.get('typ') or '—'}</td><td style='padding:8px;border:1px solid #ddd'>{fmt_date(r['datum_platnosti'])}</td><td style='padding:8px;border:1px solid #ddd;color:{barva};font-weight:bold'>{stav_}</td></tr>"

    hlavicka = "<table style='border-collapse:collapse;width:100%'><tr style='background:#2c3e50;color:white'><th style='padding:10px;border:1px solid #ddd;text-align:left'>Zařízení</th><th style='padding:10px;border:1px solid #ddd;text-align:left'>Umístění</th><th style='padding:10px;border:1px solid #ddd;text-align:left'>Typ</th><th style='padding:10px;border:1px solid #ddd;text-align:left'>Platnost</th><th style='padding:10px;border:1px solid #ddd;text-align:left'>Stav</th></tr>"

    html = f"""<html><body style='font-family:Arial,sans-serif;max-width:800px;margin:auto;padding:20px'>
    <div style='background:#2c3e50;color:white;padding:20px;border-radius:6px 6px 0 0'><h1 style='margin:0'>⚡ Hlídání elektro revizí</h1><p style='margin:5px 0 0'>{dnes.strftime('%d.%m.%Y')}</p></div>
    <div style='padding:20px;border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px'>
    {'<h2 style="color:#c0392b">❌ Prošlé revize</h2>' + hlavicka + ''.join(trow(r) for r in prosle) + '</table>' if prosle else ''}
    {'<h2 style="color:#e67e22">⚠️ Blížící se expirace</h2>' + hlavicka + ''.join(trow(r) for r in bliz) + '</table>' if bliz else ''}
    </div></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ Upozornění na elektro revize – {dnes.strftime('%d.%m.%Y')}"
    msg["From"]    = cfg["smtp_user"]
    msg["To"]      = ", ".join(cfg["prijemci"])
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"])) as s:
        s.ehlo(); s.starttls()
        s.login(cfg["smtp_user"], cfg["smtp_pass"])
        s.sendmail(cfg["smtp_user"], cfg["prijemci"], msg.as_string())

# ─── Inicializace ─────────────────────────────────────────────────────────────
init_db()

# ─── Sidebar navigace ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ Elektro revize")
    st.markdown("---")
    page = st.radio("Navigace", ["📋 Přehled", "➕ Přidat revizi", "🔔 Odeslat upozornění", "⚙️ Nastavení e-mailu"])
    st.markdown("---")
    vsechny = get_all()
    dnes    = date.today()
    prosle  = sum(1 for r in vsechny if datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() < dnes)
    blizici = sum(1 for r in vsechny if 0 <= (datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() - dnes).days <= 7)
    st.markdown(f"**Celkem revizí:** {len(vsechny)}")
    st.markdown(f"<span class='red'>**Prošlé:** {prosle}</span>", unsafe_allow_html=True)
    st.markdown(f"<span class='orange'>**Do 7 dní:** {blizici}</span>", unsafe_allow_html=True)

# ─── Stránka: Přehled ─────────────────────────────────────────────────────────
if page == "📋 Přehled":
    st.markdown("# 📋 Přehled revizí")

    if not vsechny:
        st.info("Zatím žádné revize. Přidejte první pomocí menu vlevo.")
    else:
        filtr = st.selectbox("Filtr", ["Všechny", "⚠️ Prošlé a blížící se (≤30 dní)", "❌ Pouze prošlé"])

        for r in vsechny:
            stav_txt, badge_cls, zbyvá = stav(r["datum_platnosti"])

            if filtr == "⚠️ Prošlé a blížící se (≤30 dní)" and zbyvá > 30:
                continue
            if filtr == "❌ Pouze prošlé" and zbyvá >= 0:
                continue

            with st.container():
                col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                with col1:
                    st.markdown(f"**{r['nazev']}**")
                    st.caption(r.get("umisteni") or "—")
                with col2:
                    st.markdown(f"<span style='font-size:0.8rem;color:#888'>Typ</span><br>{r.get('typ') or '—'}", unsafe_allow_html=True)
                with col3:
                    st.markdown(f"<span style='font-size:0.8rem;color:#888'>Platnost do</span><br>{fmt_date(r['datum_platnosti'])}", unsafe_allow_html=True)
                with col4:
                    st.markdown(f"<span class='status-badge {badge_cls}'>{stav_txt}</span>", unsafe_allow_html=True)
                with col5:
                    if st.button("🗑️", key=f"del_{r['id']}", help="Smazat"):
                        smazat(r["id"])
                        st.rerun()
                st.divider()

# ─── Stránka: Přidat revizi ───────────────────────────────────────────────────
elif page == "➕ Přidat revizi":
    st.markdown("# ➕ Přidat novou revizi")

    with st.form("nova_revize"):
        col1, col2 = st.columns(2)
        with col1:
            nazev    = st.text_input("Název zařízení / objektu *", placeholder="např. Rozvaděč RH-01")
            umisteni = st.text_input("Umístění",                   placeholder="např. Hala A, rozvodna")
            typ      = st.selectbox("Typ revize", ["pravidelná", "výchozí", "mimořádná", "následná"])
        with col2:
            technik     = st.text_input("Revizní technik", placeholder="Jméno technika")
            datum_rev   = st.date_input("Datum provedené revize",  value=date.today())
            datum_plat  = st.date_input("Platnost / příští revize", value=date.today() + timedelta(days=365))
        poznamka = st.text_area("Poznámka (volitelné)", height=80)

        odeslat = st.form_submit_button("✅ Přidat revizi", use_container_width=True)

    if odeslat:
        if not nazev:
            st.error("Vyplňte název zařízení.")
        else:
            pridat({
                "nazev": nazev,
                "umisteni": umisteni,
                "typ": typ,
                "datum_revize":   datum_rev.strftime("%Y-%m-%d"),
                "datum_platnosti": datum_plat.strftime("%Y-%m-%d"),
                "revizni_technik": technik,
                "poznamka": poznamka,
            })
            st.success(f"✅ Revize **{nazev}** byla přidána!")
            st.balloons()

# ─── Stránka: Odeslat upozornění ──────────────────────────────────────────────
elif page == "🔔 Odeslat upozornění":
    st.markdown("# 🔔 Odeslat e-mailová upozornění")
    cfg = nacti_config()

    if not cfg.get("smtp_user"):
        st.warning("⚠️ Nejprve nastavte e-mail v sekci **⚙️ Nastavení e-mailu**.")
    else:
        limit = date.today() + timedelta(days=7)
        k_odeslani = [r for r in vsechny
                      if datetime.strptime(r["datum_platnosti"], "%Y-%m-%d").date() <= limit
                      and not r["upozorneni_odeslano"]]

        st.info(f"Budou zahrnuta zařízení s platností do **{limit.strftime('%d.%m.%Y')}** (7 dní).")

        if not k_odeslani:
            st.success("✅ Žádné blížící se expirace. Vše v pořádku.")
        else:
            st.warning(f"Nalezeno **{len(k_odeslani)}** revizí k upozornění.")
            for r in k_odeslani:
                stav_txt, badge_cls, _ = stav(r["datum_platnosti"])
                st.markdown(f"- **{r['nazev']}** — {fmt_date(r['datum_platnosti'])} &nbsp; <span class='status-badge {badge_cls}'>{stav_txt}</span>", unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                if st.button("📧 Odeslat upozornění", use_container_width=True):
                    try:
                        odeslat_email(cfg, k_odeslani)
                        oznacit_odeslano([r["id"] for r in k_odeslani])
                        st.success(f"✅ E-mail odeslán na: {', '.join(cfg['prijemci'])}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Chyba: {e}")
            with col2:
                if st.button("🔄 Resetovat 'odesláno' (znovu odeslat vše)", use_container_width=True):
                    con = sqlite3.connect(DB_PATH)
                    con.execute("UPDATE revize SET upozorneni_odeslano=0")
                    con.commit()
                    con.close()
                    st.info("Reset proveden.")
                    st.rerun()

# ─── Stránka: Nastavení ───────────────────────────────────────────────────────
elif page == "⚙️ Nastavení e-mailu":
    st.markdown("# ⚙️ Nastavení e-mailu")
    cfg = nacti_config()

    with st.form("nastaveni"):
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("SMTP server", value=cfg.get("smtp_host", "smtp.gmail.com"))
            smtp_port = st.number_input("SMTP port",  value=int(cfg.get("smtp_port", 587)), step=1)
        with col2:
            smtp_user = st.text_input("Odesílací e-mail", value=cfg.get("smtp_user", ""))
            smtp_pass = st.text_input("Heslo / App Password", value=cfg.get("smtp_pass", ""), type="password")
        prijemci_str = st.text_input("Příjemci (oddělte čárkou)", value=", ".join(cfg.get("prijemci", [])))

        if st.form_submit_button("💾 Uložit nastavení", use_container_width=True):
            cfg.update({
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "smtp_user": smtp_user,
                "smtp_pass": smtp_pass,
                "prijemci":  [e.strip() for e in prijemci_str.split(",") if e.strip()],
            })
            uloz_config(cfg)
            st.success("✅ Nastavení uloženo!")

    st.markdown("---")
    st.markdown("""
    ### 💡 Tipy pro Gmail
    1. Zapněte **Dvoufázové ověření** ve svém Google účtu
    2. Vytvořte **App Password**: Účet Google → Zabezpečení → Hesla aplikací
    3. Použijte App Password místo běžného hesla
    4. SMTP server: `smtp.gmail.com`, port: `587`
    """)

    st.markdown("---")
    st.markdown("""
    ### 🌐 Nasazení na Streamlit Cloud (zdarma)
    1. Nahrajte soubory na **GitHub** (`app.py` + `requirements.txt`)
    2. Jděte na [share.streamlit.io](https://share.streamlit.io)
    3. Přihlaste se přes GitHub a klikněte **Deploy**
    4. Hesla zadejte přes **Secrets** (ne přímo do kódu)
    """)
