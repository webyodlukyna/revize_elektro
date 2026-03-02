"""
app.py – Pouze UI vrstva (Streamlit)
Spuštění: streamlit run app.py
"""

import streamlit as st
from datetime import date, timedelta
import io
import pandas as pd
from pathlib import Path

import database as db
import config as cfg_mod
import auth
import export


REQUIRED_IMPORT_FIELDS = ["nazev", "datum_revize", "datum_platnosti"]


def _normalize_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _normalize_col_name(col_name: str) -> str:
    return (
        col_name.strip().lower()
        .replace("á", "a")
        .replace("č", "c")
        .replace("ď", "d")
        .replace("é", "e")
        .replace("ě", "e")
        .replace("í", "i")
        .replace("ň", "n")
        .replace("ó", "o")
        .replace("ř", "r")
        .replace("š", "s")
        .replace("ť", "t")
        .replace("ú", "u")
        .replace("ů", "u")
        .replace("ý", "y")
        .replace("ž", "z")
        .replace(" ", "_")
    )


def _parse_date(value, field_name: str, row_number: int, errors: list[str]):
    if value is None or str(value).strip() == "":
        errors.append(f"Řádek {row_number}: chybí {field_name}.")
        return None
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        errors.append(f"Řádek {row_number}: neplatné datum v poli {field_name}.")
        return None
    return parsed.date()


def _prepare_import_rows(df: pd.DataFrame, existing_rows: list[dict]):
    alias_map = {
        "nazev": "nazev",
        "nazev_zarizeni": "nazev",
        "zarizeni": "nazev",
        "objekt": "nazev",
        "umisteni": "umisteni",
        "typ": "typ",
        "typ_revize": "typ",
        "datum_revize": "datum_revize",
        "provedena": "datum_revize",
        "datum_provedeni": "datum_revize",
        "datum_platnosti": "datum_platnosti",
        "platnost": "datum_platnosti",
        "pristi_revize": "datum_platnosti",
        "revizni_technik": "revizni_technik",
        "technik": "revizni_technik",
        "poznamka": "poznamka",
    }

    rename_map = {}
    for col in df.columns:
        normalized = _normalize_col_name(str(col))
        if normalized in alias_map:
            rename_map[col] = alias_map[normalized]

    normalized_df = df.rename(columns=rename_map)

    missing = [field for field in REQUIRED_IMPORT_FIELDS if field not in normalized_df.columns]
    if missing:
        return [], [
            "Soubor neobsahuje povinné sloupce: "
            + ", ".join(missing)
            + ". Povinné: nazev, datum_revize, datum_platnosti."
        ]

    db_keys = {
        (
            _normalize_text(r.get("nazev")).lower(),
            _normalize_text(r.get("umisteni")).lower(),
            _normalize_text(r.get("datum_platnosti")),
        )
        for r in existing_rows
    }

    import_keys = set()
    valid_rows = []
    errors = []

    for row_number, (_, row) in enumerate(normalized_df.iterrows(), start=2):

        nazev = _normalize_text(row.get("nazev"))
        if not nazev:
            errors.append(f"Řádek {row_number}: chybí název.")
            continue

        datum_rev = _parse_date(row.get("datum_revize"), "datum_revize", row_number, errors)
        datum_plat = _parse_date(row.get("datum_platnosti"), "datum_platnosti", row_number, errors)
        if not datum_rev or not datum_plat:
            continue

        if datum_plat < datum_rev:
            errors.append(f"Řádek {row_number}: datum_platnosti je dříve než datum_revize.")
            continue

        umisteni = _normalize_text(row.get("umisteni"))
        dedup_key = (nazev.lower(), umisteni.lower(), datum_plat.strftime("%Y-%m-%d"))
        if dedup_key in db_keys:
            errors.append(f"Řádek {row_number}: duplicita už existuje v databázi.")
            continue
        if dedup_key in import_keys:
            errors.append(f"Řádek {row_number}: duplicita v importovaném souboru.")
            continue

        import_keys.add(dedup_key)
        valid_rows.append({
            "nazev": nazev,
            "umisteni": umisteni,
            "typ": _normalize_text(row.get("typ")) or "pravidelná",
            "datum_revize": datum_rev.strftime("%Y-%m-%d"),
            "datum_platnosti": datum_plat.strftime("%Y-%m-%d"),
            "revizni_technik": _normalize_text(row.get("revizni_technik")),
            "poznamka": _normalize_text(row.get("poznamka")),
        })

    return valid_rows, errors

# ─── Konfigurace stránky ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="RP ELECTRIC SOLUTION s.r.o.",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",  # na mobilu sidebar schovaný
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

  /* Karta revize pro mobil */
  .revize-karta {
    background:#1a1d27;
    border:1px solid #2a2d3e;
    border-radius:8px;
    padding:14px 16px;
    margin-bottom:10px;
  }
  .revize-karta .nazev { font-weight:600; font-size:1rem; margin-bottom:4px; }
  .revize-karta .detail { font-size:0.82rem; color:#888; margin-bottom:6px; }

  /* Responzivní sloupce – na úzkých obrazovkách skryjeme vedlejší sloupce */
  @media (max-width: 640px) {
    .desktop-only { display: none !important; }
    h1 { font-size: 1.4rem !important; }
  }
</style>
""", unsafe_allow_html=True)

# ─── Přihlašování ────────────────────────────────────────────────────────────
auth.vyzaduj_prihlaseni()


def _current_user() -> str:
    return st.session_state.get("uzivatel", "admin")


def _is_admin() -> bool:
    return st.session_state.get("role", "admin") == "admin"


UPLOADS_DIR = Path("uploads")


def _safe_filename(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum() or ch in {"-", "_", ".", " "}).strip() or "soubor"


def _safe_date_input(value, fallback: date) -> date:
    parsed = pd.to_datetime(str(value or ""), errors="coerce")
    return fallback if pd.isna(parsed) else parsed.date()

# ─── Inicializace ─────────────────────────────────────────────────────────────
db.init_db()
dnes   = date.today()
mobil  = st.session_state.get("mobil", False)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ RP ELECTRIC SOLUTION s.r.o.")
    st.markdown("---")
    page = st.radio("Navigace", [
        "📋 Přehled",
        "➕ Přidat revizi",
        "📥 Import z Excelu",
        "📎 Přílohy a historie",
        "📅 Kalendář (ICS)",
        "🔔 Odeslat upozornění",
        "🧾 Audit log",
        "⚙️ Nastavení notifikací",
    ])
    st.markdown("---")

    vsechny = db.get_all()
    prosle  = sum(1 for r in vsechny if db.stav(r["datum_platnosti"])[2] < 0)
    blizici = sum(1 for r in vsechny if 0 <= db.stav(r["datum_platnosti"])[2] <= 7)

    st.markdown(f"**Celkem revizí:** {len(vsechny)}")
    st.markdown(f"<span style='color:#e74c3c'>**Prošlé:** {prosle}</span>",    unsafe_allow_html=True)
    st.markdown(f"<span style='color:#e67e22'>**Do 7 dní:** {blizici}</span>", unsafe_allow_html=True)
    st.markdown(f"👤 {_current_user()} ({st.session_state.get('role', 'admin')})")

    st.markdown("---")
    if st.button("🔒 Odhlásit se", use_container_width=True):
        db.log_akce("logout", "Uživatel se odhlásil", _current_user())
        st.session_state["prihlaseno"] = False
        st.rerun()


# ─── Přehled ──────────────────────────────────────────────────────────────────
if page == "📋 Přehled":
    st.markdown("# 📋 Přehled revizí")

    if not vsechny:
        st.info("Zatím žádné revize. Přidejte první pomocí menu vlevo.")
    else:
        vse_typy = sorted({(r.get("typ") or "").strip() for r in vsechny if (r.get("typ") or "").strip()})
        vse_technici = sorted({(r.get("revizni_technik") or "").strip() for r in vsechny if (r.get("revizni_technik") or "").strip()})
        vse_umisteni = sorted({(r.get("umisteni") or "").strip() for r in vsechny if (r.get("umisteni") or "").strip()})

        hledat = st.text_input(
            "Hledat (název, umístění, typ, technik, poznámka)",
            placeholder="např. RH-01, Hala A, mimořádná...",
        ).strip().lower()

        col1, col2, col3 = st.columns(3)
        with col1:
            filtr_stav = st.selectbox("Stav", [
                "Všechny",
                "⚠️ Prošlé a blížící se (≤ 30 dní)",
                "❌ Pouze prošlé",
                "✅ Pouze platné",
            ])
        with col2:
            filtr_typ = st.selectbox("Typ revize", ["Všechny"] + vse_typy)
        with col3:
            filtr_technik = st.selectbox("Revizní technik", ["Všichni"] + vse_technici)

        filtr_umisteni = st.selectbox("Umístění", ["Všechna"] + vse_umisteni)

        filtrovane = []
        for r in vsechny:
            stav_txt, badge_cls, zbyva = db.stav(r["datum_platnosti"])

            if filtr_stav == "⚠️ Prošlé a blížící se (≤ 30 dní)" and zbyva > 30:
                continue
            if filtr_stav == "❌ Pouze prošlé" and zbyva >= 0:
                continue
            if filtr_stav == "✅ Pouze platné" and zbyva < 0:
                continue

            if filtr_typ != "Všechny" and (r.get("typ") or "").strip() != filtr_typ:
                continue
            if filtr_technik != "Všichni" and (r.get("revizni_technik") or "").strip() != filtr_technik:
                continue
            if filtr_umisteni != "Všechna" and (r.get("umisteni") or "").strip() != filtr_umisteni:
                continue

            if hledat:
                searchable = " ".join([
                    (r.get("nazev") or ""),
                    (r.get("umisteni") or ""),
                    (r.get("typ") or ""),
                    (r.get("revizni_technik") or ""),
                    (r.get("poznamka") or ""),
                ]).lower()
                if hledat not in searchable:
                    continue

            filtrovane.append((r, stav_txt, badge_cls))

        col_info, col_export_pdf, col_export_csv, col_export_xlsx = st.columns([2, 1, 1, 1])
        with col_info:
            st.caption(f"Zobrazeno: {len(filtrovane)} z {len(vsechny)} revizí")
        with col_export_pdf:
            pdf_bytes = export.generuj_pdf([item[0] for item in filtrovane], f"Pokročilý filtr: {filtr_stav}")
            st.download_button(
                label="📄 Export PDF",
                data=pdf_bytes,
                file_name=f"revize_{dnes.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        export_rows = []
        for r, stav_txt, _, in filtrovane:
            export_rows.append({
                "ID": r.get("id"),
                "Název": r.get("nazev") or "",
                "Umístění": r.get("umisteni") or "",
                "Typ": r.get("typ") or "",
                "Datum revize": db.fmt_date(r.get("datum_revize")) if r.get("datum_revize") else "",
                "Platnost do": db.fmt_date(r.get("datum_platnosti")) if r.get("datum_platnosti") else "",
                "Revizní technik": r.get("revizni_technik") or "",
                "Poznámka": r.get("poznamka") or "",
                "Stav": stav_txt,
            })

        export_df = pd.DataFrame(export_rows)

        with col_export_csv:
            csv_bytes = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📄 Export CSV",
                data=csv_bytes,
                file_name=f"revize_{dnes.strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
                disabled=export_df.empty,
            )

        with col_export_xlsx:
            xlsx_buffer = io.BytesIO()
            with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="Revize")
            st.download_button(
                label="📊 Export XLSX",
                data=xlsx_buffer.getvalue(),
                file_name=f"revize_{dnes.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=export_df.empty,
            )

        if not filtrovane:
            st.info("Žádné revize neodpovídají zadaným filtrům.")

        for r, stav_txt, badge_cls in filtrovane:
            st.markdown(f"""
            <div class="revize-karta">
              <div class="nazev">{r['nazev']}</div>
              <div class="detail">
                📍 {r.get('umisteni') or '—'} &nbsp;·&nbsp;
                🔧 {r.get('typ') or '—'} &nbsp;·&nbsp;
                👷 {r.get('revizni_technik') or '—'} &nbsp;·&nbsp;
                📅 {db.fmt_date(r['datum_platnosti'])}
              </div>
              <span class="status-badge {badge_cls}">{stav_txt}</span>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🗑️ Smazat", key=f"del_{r['id']}", disabled=not _is_admin()):
                db.pridej_historii(r["id"], "before_delete", r, _current_user())
                db.smazat(r["id"])
                db.log_akce("delete_revize", f"Smazána revize: {r.get('nazev', '')}", _current_user())
                st.rerun()


# ─── Přidat revizi ────────────────────────────────────────────────────────────
elif page == "➕ Přidat revizi":
    st.markdown("# ➕ Přidat novou revizi")

    with st.form("nova_revize"):
        nazev    = st.text_input("Název zařízení / objektu *", placeholder="např. Rozvaděč RH-01")
        umisteni = st.text_input("Umístění", placeholder="např. Hala A, rozvodna")
        typ      = st.selectbox("Typ revize", ["pravidelná", "výchozí", "mimořádná", "následná"])
        technik  = st.text_input("Revizní technik", placeholder="Jméno technika")

        # Na mobilu pod sebou, na desktopu vedle sebe
        col1, col2 = st.columns([1, 1])
        with col1:
            datum_rev  = st.date_input("Datum provedené revize",  value=dnes)
        with col2:
            datum_plat = st.date_input("Platnost / příští revize", value=dnes + timedelta(days=365))

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
            db.log_akce("create_revize", f"Přidána revize: {nazev}", _current_user())
            st.success(f"✅ Revize **{nazev}** byla přidána!")
            st.balloons()


# ─── Import z Excelu ─────────────────────────────────────────────────────────
elif page == "📥 Import z Excelu":
    st.markdown("# 📥 Import revizí z Excelu")
    if not _is_admin():
        st.warning("Tato sekce je dostupná pouze pro roli admin.")
        st.stop()

    st.caption("Podporované formáty: .xlsx, .xls")
    st.markdown(
        "**Očekávané sloupce:** `nazev`, `datum_revize`, `datum_platnosti`  "+
        "(volitelné: `umisteni`, `typ`, `revizni_technik`, `poznamka`)"
    )

    excel_file = st.file_uploader("Nahrajte Excel soubor", type=["xlsx", "xls"])

    if excel_file is not None:
        try:
            df = pd.read_excel(excel_file)
            if df.empty:
                st.warning("Soubor je prázdný.")
            else:
                st.success(f"Načteno řádků: {len(df)}")
                with st.expander("Náhled dat"):
                    st.dataframe(df.head(20), use_container_width=True)

                valid_rows, import_errors = _prepare_import_rows(df, db.get_all())

                col_ok, col_err = st.columns(2)
                col_ok.metric("Validní řádky", len(valid_rows))
                col_err.metric("Chybné / duplicitní", len(import_errors))

                if import_errors:
                    with st.expander("Zobrazit chyby validace"):
                        for err in import_errors:
                            st.write(f"- {err}")

                if valid_rows:
                    if st.button("✅ Importovat validní řádky", use_container_width=True):
                        for row_data in valid_rows:
                            db.pridat(row_data)
                        db.log_akce("import_excel", f"Importováno řádků: {len(valid_rows)}", _current_user())
                        st.success(f"Import dokončen. Přidáno {len(valid_rows)} revizí.")
                        st.rerun()
                else:
                    st.info("Žádné řádky k importu.")
        except Exception as e:
            st.error(f"Soubor se nepodařilo načíst: {e}")


# ─── Přílohy a historie ─────────────────────────────────────────────────────
elif page == "📎 Přílohy a historie":
    st.markdown("# 📎 Přílohy a historie revize")

    if not vsechny:
        st.info("Nejsou dostupné žádné revize.")
        st.stop()

    labels = [f"{r['id']} · {r.get('nazev') or 'Bez názvu'} · {db.fmt_date(r['datum_platnosti'])}" for r in vsechny]
    selected_label = st.selectbox("Vyberte revizi", labels)
    selected_id = int(selected_label.split(" · ")[0])
    selected = next((r for r in vsechny if r["id"] == selected_id), None)

    if not selected:
        st.warning("Vybraná revize nebyla nalezena.")
        st.stop()

    st.markdown("### ✏️ Editace revize")
    typ_options = ["pravidelná", "výchozí", "mimořádná", "následná"]
    selected_typ = str(selected.get("typ") or "")
    typ_index = typ_options.index(selected_typ) if selected_typ in typ_options else 0

    with st.form(f"edit_revize_{selected_id}"):
        e_nazev = st.text_input("Název", value=selected.get("nazev") or "")
        e_umisteni = st.text_input("Umístění", value=selected.get("umisteni") or "")
        e_typ = st.selectbox(
            "Typ revize",
            typ_options,
            index=typ_index,
        )
        e_technik = st.text_input("Revizní technik", value=selected.get("revizni_technik") or "")

        c1, c2 = st.columns(2)
        with c1:
            e_datum_rev = st.date_input(
                "Datum revize",
                value=_safe_date_input(selected.get("datum_revize"), dnes),
            )
        with c2:
            e_datum_plat = st.date_input(
                "Datum platnosti",
                value=_safe_date_input(selected.get("datum_platnosti"), dnes),
            )

        e_poznamka = st.text_area("Poznámka", value=selected.get("poznamka") or "", height=80)
        ulozit_edit = st.form_submit_button("💾 Uložit změny", use_container_width=True, disabled=not _is_admin())

    if ulozit_edit:
        if not e_nazev.strip():
            st.error("Název je povinný.")
        elif e_datum_plat < e_datum_rev:
            st.error("Datum platnosti nesmí být dříve než datum revize.")
        else:
            db.pridej_historii(selected_id, "before_update", selected, _current_user())
            new_data = {
                "nazev": e_nazev.strip(),
                "umisteni": e_umisteni.strip(),
                "typ": e_typ,
                "datum_revize": e_datum_rev.strftime("%Y-%m-%d"),
                "datum_platnosti": e_datum_plat.strftime("%Y-%m-%d"),
                "revizni_technik": e_technik.strip(),
                "poznamka": e_poznamka,
            }
            db.update_revize(selected_id, new_data)
            db.pridej_historii(selected_id, "after_update", {"id": selected_id, **new_data}, _current_user())
            db.log_akce("update_revize", f"Upravena revize: {new_data['nazev']}", _current_user())
            st.success("Revize byla upravena.")
            st.rerun()

    st.markdown("---")
    st.markdown("### 📎 Přílohy")
    uploaded_files = st.file_uploader(
        "Nahrát soubory k revizi",
        type=["pdf", "jpg", "jpeg", "png", "doc", "docx", "xlsx", "xls", "txt"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("⬆️ Uložit přílohy", use_container_width=True, disabled=not _is_admin()):
        saved_count = 0
        target_dir = UPLOADS_DIR / str(selected_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        for f in uploaded_files:
            safe_name = _safe_filename(f.name)
            ts_name = f"{date.today().strftime('%Y%m%d')}_{safe_name}"
            target_file = target_dir / ts_name
            target_file.write_bytes(f.getbuffer())
            db.uloz_prilohu(selected_id, f.name, str(target_file), _current_user())
            saved_count += 1

        db.log_akce("upload_priloha", f"Nahráno příloh: {saved_count} (revize {selected_id})", _current_user())
        st.success(f"Uloženo {saved_count} příloh.")
        st.rerun()

    prilohy = db.get_prilohy(selected_id)
    if not prilohy:
        st.caption("K revizi zatím nejsou žádné přílohy.")
    else:
        for p in prilohy:
            file_path = Path(str(p.get("file_path") or ""))
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.markdown(f"**{p.get('file_name', 'soubor')}** · {p.get('uploaded_at', '')} · {p.get('uploaded_by', '')}")
                if file_path.exists():
                    st.download_button(
                        label="⬇️ Stáhnout",
                        data=file_path.read_bytes(),
                        file_name=p.get("file_name") or file_path.name,
                        use_container_width=False,
                        key=f"download_priloha_{p.get('id')}",
                    )
                else:
                    st.caption("Soubor na disku nebyl nalezen.")
            with col_b:
                if st.button("🗑️", key=f"del_priloha_{p.get('id')}", disabled=not _is_admin()):
                    if file_path.exists():
                        file_path.unlink()
                    db.smazat_prilohu(int(p["id"]))
                    db.log_akce("delete_priloha", f"Smazána příloha {p.get('file_name')} (revize {selected_id})", _current_user())
                    st.rerun()

    st.markdown("---")
    st.markdown("### 🕓 Historie verzí")
    historie = db.get_historie(selected_id, limit=200)
    if not historie:
        st.caption("Pro tuto revizi zatím není historie změn.")
    else:
        hist_rows = []
        for item in historie:
            snapshot = item.get("snapshot_json") or ""
            snapshot_preview = snapshot[:180] + ("..." if len(snapshot) > 180 else "")
            hist_rows.append({
                "Čas": item.get("changed_at"),
                "Uživatel": item.get("changed_by"),
                "Akce": item.get("action"),
                "Snapshot": snapshot_preview,
            })
        st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)


# ─── Kalendář (ICS) ─────────────────────────────────────────────────────────
elif page == "📅 Kalendář (ICS)":
    st.markdown("# 📅 Export kalendáře (.ics)")
    st.caption("Export funguje pro Outlook, Google Calendar, Apple Calendar i mobilní kalendáře.")

    col_h, col_flags = st.columns([2, 2])
    with col_h:
        horizon_days = st.slider("Horizont exportu (dny)", min_value=7, max_value=730, value=90, step=1)
    with col_flags:
        include_overdue = st.checkbox("Zahrnout i prošlé revize", value=False)

    k_exportu = []
    for r in vsechny:
        parsed = pd.to_datetime(str(r.get("datum_platnosti") or ""), errors="coerce")
        if pd.isna(parsed):
            continue
        delta = (parsed.date() - dnes).days
        if include_overdue:
            if delta <= horizon_days:
                k_exportu.append(r)
        else:
            if 0 <= delta <= horizon_days:
                k_exportu.append(r)

    st.info(f"Vybráno událostí do kalendáře: **{len(k_exportu)}**")

    if k_exportu:
        preview_rows = []
        for r in k_exportu:
            stav_txt, _, _ = db.stav(r["datum_platnosti"])
            preview_rows.append({
                "Název": r.get("nazev") or "",
                "Umístění": r.get("umisteni") or "",
                "Typ": r.get("typ") or "",
                "Platnost": db.fmt_date(r.get("datum_platnosti")),
                "Stav": stav_txt,
            })
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    ics_bytes = export.generuj_ics(k_exportu)
    if st.download_button(
        label="📅 Stáhnout kalendář (.ics)",
        data=ics_bytes,
        file_name=f"revize_kalendar_{dnes.strftime('%Y%m%d')}.ics",
        mime="text/calendar",
        use_container_width=True,
        disabled=not bool(k_exportu),
    ):
        db.log_akce("export_ics", f"Exportováno {len(k_exportu)} událostí do ICS", _current_user())
        st.success("ICS export připraven.")


# ─── Odeslat upozornění ───────────────────────────────────────────────────────
elif page == "🔔 Odeslat upozornění":
    st.markdown("# 🔔 Odeslat upozornění")
    config = cfg_mod.nacti_config()
    email_ready = cfg_mod.config_ok(config)
    webhook_ready = cfg_mod.webhook_ok(config)

    if not email_ready and not webhook_ready:
        st.warning("⚠️ Nejprve nastavte e-mail nebo webhook v sekci **⚙️ Nastavení notifikací**.")
    else:
        st.markdown("### Kanály odeslání")
        send_email = st.checkbox("📧 E-mail", value=email_ready, disabled=not email_ready)
        send_webhook = st.checkbox("🌐 Webhook / SMS brána", value=webhook_ready, disabled=not webhook_ready)

        col_days, col_sent = st.columns([2, 1])
        with col_days:
            dny_horizont = st.slider("Horizont upozornění (dny)", min_value=1, max_value=90, value=7, step=1)
        with col_sent:
            zahrnout_odeslane = st.checkbox("Zahrnout i již odeslané", value=False)

        limit_txt = (dnes + timedelta(days=dny_horizont)).strftime("%d.%m.%Y")
        st.info(f"Zahrnuta zařízení s platností do **{limit_txt}** ({dny_horizont} dní).")

        if zahrnout_odeslane:
            k_odeslani = []
            for r in db.get_all():
                parsed = pd.to_datetime(str(r.get("datum_platnosti") or ""), errors="coerce")
                if pd.isna(parsed):
                    continue
                if (parsed.date() - dnes).days <= dny_horizont:
                    k_odeslani.append(r)
        else:
            k_odeslani = db.get_k_odeslani(days=dny_horizont)

        if not k_odeslani:
            st.success("✅ Žádné blížící se expirace. Vše v pořádku.")
        else:
            prosle = []
            do_7 = []
            do_horizontu = []

            for r in k_odeslani:
                _, _, zbyva = db.stav(r["datum_platnosti"])
                if zbyva < 0:
                    prosle.append(r)
                elif zbyva <= 7:
                    do_7.append(r)
                else:
                    do_horizontu.append(r)

            st.warning(f"Nalezeno **{len(k_odeslani)}** revizí k upozornění.")
            met1, met2, met3 = st.columns(3)
            met1.metric("❌ Prošlé", len(prosle))
            met2.metric("⚠️ Do 7 dní", len(do_7))
            met3.metric(f"🔔 Do {dny_horizont} dní", len(do_horizontu))

            for title, items in [
                ("❌ Prošlé", prosle),
                ("⚠️ Blížící se (do 7 dní)", do_7),
                (f"🔔 Další v horizontu ({dny_horizont} dní)", do_horizontu),
            ]:
                if items:
                    st.markdown(f"**{title}**")
                    for r in items:
                        stav_txt, badge_cls, _ = db.stav(r["datum_platnosti"])
                        st.markdown(
                            f"- **{r['nazev']}** — {db.fmt_date(r['datum_platnosti'])} &nbsp;"
                            f"<span class='status-badge {badge_cls}'>{stav_txt}</span>",
                            unsafe_allow_html=True,
                        )

            st.markdown("")
            if st.button("📧 Odeslat upozornění", use_container_width=True, disabled=not _is_admin()):
                try:
                    if not send_email and not send_webhook:
                        st.error("Vyberte alespoň jeden kanál odeslání.")
                        st.stop()

                    if send_email:
                        cfg_mod.odeslat_email(config, k_odeslani)
                    if send_webhook:
                        cfg_mod.odeslat_webhook(config, k_odeslani)

                    db.oznacit_odeslano([r["id"] for r in k_odeslani])
                    kanal_txt = []
                    if send_email:
                        kanal_txt.append("e-mail")
                    if send_webhook:
                        kanal_txt.append("webhook")
                    db.log_akce("send_alert", f"Odesláno upozornění pro {len(k_odeslani)} revizí ({', '.join(kanal_txt)})", _current_user())

                    if send_email and send_webhook:
                        st.success(f"✅ Upozornění odesláno e-mailem i webhookem ({len(k_odeslani)} revizí).")
                    elif send_email:
                        st.success(f"✅ E-mail odeslán na: {', '.join(config['prijemci'])}")
                    else:
                        st.success(f"✅ Webhook odeslán ({len(k_odeslani)} revizí).")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Chyba při odesílání: {e}")

            if st.button("🔄 Resetovat 'odesláno'", use_container_width=True, disabled=not _is_admin()):
                db.reset_odeslano()
                db.log_akce("reset_alert_flag", "Resetován příznak upozornění", _current_user())
                st.info("Reset proveden — všechna upozornění lze odeslat znovu.")
                st.rerun()


# ─── Audit log ───────────────────────────────────────────────────────────────
elif page == "🧾 Audit log":
    st.markdown("# 🧾 Audit log")
    if not _is_admin():
        st.warning("Tato sekce je dostupná pouze pro roli admin.")
        st.stop()

    limit = st.slider("Počet záznamů", min_value=20, max_value=500, value=100, step=20)
    logs = db.get_audit(limit=limit)

    if not logs:
        st.info("Audit log je zatím prázdný.")
    else:
        df_logs = pd.DataFrame(logs)
        rename_map = {
            "created_at": "Čas",
            "user_name": "Uživatel",
            "action": "Akce",
            "detail": "Detail",
        }
        df_logs = df_logs.rename(columns=rename_map)
        cols = [c for c in ["Čas", "Uživatel", "Akce", "Detail"] if c in df_logs.columns]
        st.dataframe(df_logs[cols], use_container_width=True, hide_index=True)

        csv_logs = df_logs.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "📄 Export audit logu (CSV)",
            data=csv_logs,
            file_name=f"audit_log_{dnes.strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ─── Nastavení notifikací ───────────────────────────────────────────────────
elif page == "⚙️ Nastavení notifikací":
    st.markdown("# ⚙️ Nastavení notifikací")
    if not _is_admin():
        st.warning("Tato sekce je dostupná pouze pro roli admin.")
        st.stop()

    config = cfg_mod.nacti_config()

    with st.form("nastaveni"):
        smtp_host    = st.text_input("SMTP server",           value=config.get("smtp_host", "smtp.gmail.com"))
        smtp_port    = st.number_input("SMTP port",           value=int(config.get("smtp_port", 587)), step=1)
        smtp_user    = st.text_input("Odesílací e-mail",      value=config.get("smtp_user", ""))
        smtp_pass    = st.text_input("Heslo / App Password",  value=config.get("smtp_pass", ""), type="password")
        prijemci_str = st.text_input(
            "Příjemci (oddělte čárkou)",
            value=", ".join(config.get("prijemci", [])),
        )
        webhook_url  = st.text_input(
            "Webhook URL (volitelné)",
            value=config.get("webhook_url", ""),
            placeholder="https://...",
        )

        if st.form_submit_button("💾 Uložit nastavení", use_container_width=True):
            cfg_mod.uloz_config({
                "smtp_host": smtp_host,
                "smtp_port": int(smtp_port),
                "smtp_user": smtp_user,
                "smtp_pass": smtp_pass,
                "prijemci":  [e.strip() for e in prijemci_str.split(",") if e.strip()],
                "webhook_url": str(webhook_url or "").strip(),
            })
            db.log_akce("update_config", "Upraveno nastavení e-mailu/webhooku", _current_user())
            st.success("✅ Nastavení uloženo!")

    st.markdown("---")
    st.markdown("### 🔌 Test připojení k databázi")
    if st.button("🔍 Otestovat připojení", use_container_width=True):
        try:
            db.init_db()
            pocet = len(db.get_all())
            if db._je_supabase():
                st.success(f"✅ Supabase připojeno! Počet revizí v databázi: **{pocet}**")
            else:
                st.success(f"✅ SQLite připojeno (lokální režim). Počet revizí: **{pocet}**")
        except Exception as e:
            st.error(f"❌ Připojení selhalo: {e}")

    st.markdown("---")
    st.markdown("""
    ### RP ELECTRIC SOLUTION s.r.o. | Revize bez kompromisů
    """)
