"""
app.py – Pouze UI vrstva (Streamlit)
Spuštění: streamlit run app.py
"""

import streamlit as st
from datetime import date, timedelta

import database as db
import config as cfg_mod
import auth

# ─── Konfigurace stránky ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Elektro revize",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
  h1, h2, h3 { font-family: 'IBM Plex Mono', monospace !important; }
  .stApp { background-color: #0f1117; color: #e0e0e0; }

  .status-badge { display:inline-block; padding:3px 10px; border-radius:12px;
                  font-size:0.78rem; font-weight:600; font-family:'IBM Plex Mono',monospace; }
  .badge-red    { background:#3d1a1a; color:#e74c3c; border:1px solid #e74c3c44; }
  .badge-orange { background:#3d2a1a; color:#e67e22; border:1px solid #e67e2244; }
  .badge-green  { background:#1a3d2a; color:#2ecc71; border:1px solid #2ecc7144; }

  div[data-testid="stSidebar"] { background:#13151f; border-right:1px solid #2a2d3e; }

  .stButton > button {
    background:#1a1d27; color:#e0e0e0; border:1px solid #3a3d4e;
    border-radius:6px; font-family:'IBM Plex Mono',monospace; font-size:0.85rem; transition:all 0.2s;
  }
  .stButton > button:hover { background:#252839; border-color:#5a8dee; color:#5a8dee; }

  .stTextInput > div > div > input,
  .stSelectbox > div > div,
  .stDateInput > div > div > input,
  .stTextArea textarea {
    background:#1a1d27 !important; border:1px solid #2a2d3e !important;
    color:#e0e0e0 !important; border-radius:6px !important;
  }
  hr { border-color:#2a2d3e !important; }
</style>
""", unsafe_allow_html=True)

# ─── Přihlašování ────────────────────────────────────────────────────────────
auth.vyzaduj_prihlaseni()

# ─── Inicializace ─────────────────────────────────────────────────────────────
db.init_db()
dnes = date.today()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ Elektro revize")
    st.markdown("---")
    page = st.radio("Navigace", [
        "📋 Přehled",
        "➕ Přidat revizi",
        "🔔 Odeslat upozornění",
        "⚙️ Nastavení e-mailu",
    ])
    st.markdown("---")

    vsechny = db.get_all()
    prosle  = sum(1 for r in vsechny if db.stav(r["datum_platnosti"])[2] < 0)
    blizici = sum(1 for r in vsechny if 0 <= db.stav(r["datum_platnosti"])[2] <= 7)

    st.markdown(f"**Celkem revizí:** {len(vsechny)}")
    st.markdown(f"<span style='color:#e74c3c'>**Prošlé:** {prosle}</span>",   unsafe_allow_html=True)
    st.markdown(f"<span style='color:#e67e22'>**Do 7 dní:** {blizici}</span>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔒 Odhlásit se", use_container_width=True):
        st.session_state["prihlaseno"] = False
        st.rerun()


# ─── Přehled ──────────────────────────────────────────────────────────────────
if page == "📋 Přehled":
    st.markdown("# 📋 Přehled revizí")

    if not vsechny:
        st.info("Zatím žádné revize. Přidejte první pomocí menu vlevo.")
    else:
        filtr = st.selectbox("Filtr", [
            "Všechny",
            "⚠️ Prošlé a blížící se (≤ 30 dní)",
            "❌ Pouze prošlé",
        ])

        for r in vsechny:
            stav_txt, badge_cls, zbyvá = db.stav(r["datum_platnosti"])

            if filtr == "⚠️ Prošlé a blížící se (≤ 30 dní)" and zbyvá > 30:
                continue
            if filtr == "❌ Pouze prošlé" and zbyvá >= 0:
                continue

            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
            with col1:
                st.markdown(f"**{r['nazev']}**")
                st.caption(r.get("umisteni") or "—")
            with col2:
                st.markdown(f"<span style='font-size:0.8rem;color:#888'>Typ</span><br>{r.get('typ') or '—'}", unsafe_allow_html=True)
            with col3:
                st.markdown(f"<span style='font-size:0.8rem;color:#888'>Platnost do</span><br>{db.fmt_date(r['datum_platnosti'])}", unsafe_allow_html=True)
            with col4:
                st.markdown(f"<span class='status-badge {badge_cls}'>{stav_txt}</span>", unsafe_allow_html=True)
            with col5:
                if st.button("🗑️", key=f"del_{r['id']}", help="Smazat"):
                    db.smazat(r["id"])
                    st.rerun()
            st.divider()


# ─── Přidat revizi ────────────────────────────────────────────────────────────
elif page == "➕ Přidat revizi":
    st.markdown("# ➕ Přidat novou revizi")

    with st.form("nova_revize"):
        col1, col2 = st.columns(2)
        with col1:
            nazev    = st.text_input("Název zařízení / objektu *", placeholder="např. Rozvaděč RH-01")
            umisteni = st.text_input("Umístění", placeholder="např. Hala A, rozvodna")
            typ      = st.selectbox("Typ revize", ["pravidelná", "výchozí", "mimořádná", "následná"])
        with col2:
            technik    = st.text_input("Revizní technik", placeholder="Jméno technika")
            datum_rev  = st.date_input("Datum provedené revize",   value=dnes)
            datum_plat = st.date_input("Platnost / příští revize",  value=dnes + timedelta(days=365))
        poznamka = st.text_area("Poznámka (volitelné)", height=80)
        odeslat  = st.form_submit_button("✅ Přidat revizi", use_container_width=True)

    if odeslat:
        if not nazev:
            st.error("Vyplňte název zařízení.")
        else:
            db.pridat({
                "nazev":           nazev,
                "umisteni":        umisteni,
                "typ":             typ,
                "datum_revize":    datum_rev.strftime("%Y-%m-%d"),
                "datum_platnosti": datum_plat.strftime("%Y-%m-%d"),
                "revizni_technik": technik,
                "poznamka":        poznamka,
            })
            st.success(f"✅ Revize **{nazev}** byla přidána!")
            st.balloons()


# ─── Odeslat upozornění ───────────────────────────────────────────────────────
elif page == "🔔 Odeslat upozornění":
    st.markdown("# 🔔 Odeslat e-mailová upozornění")
    config = cfg_mod.nacti_config()

    if not cfg_mod.config_ok(config):
        st.warning("⚠️ Nejprve nastavte e-mail v sekci **⚙️ Nastavení e-mailu**.")
    else:
        k_odeslani = db.get_k_odeslani(days=7)
        limit_txt  = (dnes + timedelta(days=7)).strftime("%d.%m.%Y")
        st.info(f"Zahrnuta zařízení s platností do **{limit_txt}** (7 dní).")

        if not k_odeslani:
            st.success("✅ Žádné blížící se expirace. Vše v pořádku.")
        else:
            st.warning(f"Nalezeno **{len(k_odeslani)}** revizí k upozornění.")
            for r in k_odeslani:
                stav_txt, badge_cls, _ = db.stav(r["datum_platnosti"])
                st.markdown(
                    f"- **{r['nazev']}** — {db.fmt_date(r['datum_platnosti'])} &nbsp;"
                    f"<span class='status-badge {badge_cls}'>{stav_txt}</span>",
                    unsafe_allow_html=True,
                )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("📧 Odeslat upozornění", use_container_width=True):
                    try:
                        cfg_mod.odeslat_email(config, k_odeslani)
                        db.oznacit_odeslano([r["id"] for r in k_odeslani])
                        st.success(f"✅ E-mail odeslán na: {', '.join(config['prijemci'])}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Chyba při odesílání: {e}")
            with col2:
                if st.button("🔄 Resetovat 'odesláno'", use_container_width=True):
                    db.reset_odeslano()
                    st.info("Reset proveden — všechna upozornění lze odeslat znovu.")
                    st.rerun()


# ─── Nastavení e-mailu ────────────────────────────────────────────────────────
elif page == "⚙️ Nastavení e-mailu":
    st.markdown("# ⚙️ Nastavení e-mailu")
    config = cfg_mod.nacti_config()

    with st.form("nastaveni"):
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("SMTP server", value=config.get("smtp_host", "smtp.gmail.com"))
            smtp_port = st.number_input("SMTP port",  value=int(config.get("smtp_port", 587)), step=1)
        with col2:
            smtp_user = st.text_input("Odesílací e-mail",     value=config.get("smtp_user", ""))
            smtp_pass = st.text_input("Heslo / App Password", value=config.get("smtp_pass", ""), type="password")
        prijemci_str = st.text_input(
            "Příjemci (oddělte čárkou)",
            value=", ".join(config.get("prijemci", [])),
        )

        if st.form_submit_button("💾 Uložit nastavení", use_container_width=True):
            cfg_mod.uloz_config({
                "smtp_host": smtp_host,
                "smtp_port": int(smtp_port),
                "smtp_user": smtp_user,
                "smtp_pass": smtp_pass,
                "prijemci":  [e.strip() for e in prijemci_str.split(",") if e.strip()],
            })
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
    1. Nahrajte všechny `.py` soubory na **GitHub**
    2. Jděte na [share.streamlit.io](https://share.streamlit.io)
    3. Přihlaste se přes GitHub a klikněte **Deploy**
    4. Heslo zadejte přes **Secrets** v dashboardu (ne přímo do kódu)
    """)
