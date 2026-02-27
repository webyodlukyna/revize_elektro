"""
database.py – Databázová vrstva
================================
Lokálně:  SQLite (revize_elektro.db)
Cloud:    Supabase Python klient (bez psycopg2, bez IPv4 problémů)

Streamlit Secrets pro Supabase:
  [supabase]
  url = "https://XXXX.supabase.co"
  key = "eyJ..."   ← anon/public klíč z Supabase → Settings → API
"""

from datetime import date, datetime, timedelta


# ─── Detekce prostředí ────────────────────────────────────────────────────────

def _je_supabase() -> bool:
    try:
        import streamlit as st
        _ = st.secrets["supabase"]["url"]
        _ = st.secrets["supabase"]["key"]
        return True
    except Exception:
        return False


def _supabase_client():
    """Vrátí Supabase klienta."""
    import streamlit as st
    from supabase import create_client
    return create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"],
    )


# ─── Inicializace tabulky ─────────────────────────────────────────────────────

def init_db() -> None:
    """
    Lokálně: vytvoří SQLite tabulku.
    Supabase: tabulka se vytváří ručně v Supabase SQL editoru (viz návod níže).
    """
    if _je_supabase():
        # Ověř připojení jednoduchým dotazem
        _supabase_client().table("revize").select("id").limit(1).execute()
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS revize (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nazev               TEXT NOT NULL,
                umisteni            TEXT,
                typ                 TEXT,
                datum_revize        TEXT NOT NULL,
                datum_platnosti     TEXT NOT NULL,
                revizni_technik     TEXT,
                poznamka            TEXT,
                upozorneni_odeslano INTEGER DEFAULT 0
            )
        """)


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def get_all() -> list[dict]:
    if _je_supabase():
        res = _supabase_client().table("revize").select("*").order("datum_platnosti").execute()
        return res.data or []

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM revize ORDER BY datum_platnosti").fetchall()
    return [dict(r) for r in rows]


def pridat(data: dict) -> None:
    if _je_supabase():
        _supabase_client().table("revize").insert(data).execute()
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute("""
            INSERT INTO revize (nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka)
            VALUES (:nazev, :umisteni, :typ, :datum_revize, :datum_platnosti, :revizni_technik, :poznamka)
        """, data)


def smazat(rid: int) -> None:
    if _je_supabase():
        _supabase_client().table("revize").delete().eq("id", rid).execute()
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute("DELETE FROM revize WHERE id = ?", (rid,))


def oznacit_odeslano(ids: list[int]) -> None:
    if not ids:
        return
    if _je_supabase():
        _supabase_client().table("revize").update({"upozorneni_odeslano": 1}).in_("id", ids).execute()
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute(
            f"UPDATE revize SET upozorneni_odeslano = 1 WHERE id IN ({','.join('?'*len(ids))})",
            ids
        )


def reset_odeslano() -> None:
    if _je_supabase():
        _supabase_client().table("revize").update({"upozorneni_odeslano": 0}).neq("id", 0).execute()
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute("UPDATE revize SET upozorneni_odeslano = 0")


def get_k_odeslani(days: int = 7) -> list[dict]:
    limit = (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")

    if _je_supabase():
        res = (
            _supabase_client().table("revize")
            .select("*")
            .lte("datum_platnosti", limit)
            .eq("upozorneni_odeslano", 0)
            .order("datum_platnosti")
            .execute()
        )
        return res.data or []

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT * FROM revize
            WHERE datum_platnosti <= ? AND upozorneni_odeslano = 0
            ORDER BY datum_platnosti
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ─── Pomocné funkce ───────────────────────────────────────────────────────────

def stav(datum_platnosti: str) -> tuple[str, str, int]:
    plat  = datetime.strptime(datum_platnosti, "%Y-%m-%d").date()
    zbyvá = (plat - date.today()).days
    if zbyvá < 0:
        return "❌ Prošlá", "badge-red", zbyvá
    elif zbyvá <= 7:
        return f"⚠️ Za {zbyvá} dní", "badge-orange", zbyvá
    elif zbyvá <= 30:
        return f"🔔 Za {zbyvá} dní", "badge-orange", zbyvá
    else:
        return f"✅ Za {zbyvá} dní", "badge-green", zbyvá


def fmt_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y") if d else "—"
