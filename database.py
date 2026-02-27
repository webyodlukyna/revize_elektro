"""
database.py – Databázová vrstva
================================
Lokálně:  SQLite (revize_elektro.db)
Cloud:    PostgreSQL přes Supabase (st.secrets["supabase"])

Streamlit Secrets pro Supabase:
  [supabase]
  url = "postgresql://postgres:<heslo>@db.<project>.supabase.co:5432/postgres"
"""

from datetime import date, datetime, timedelta

# ─── Detekce prostředí ────────────────────────────────────────────────────────

def _je_supabase() -> bool:
    try:
        import streamlit as st
        _ = st.secrets["supabase"]["url"]
        return True
    except Exception:
        return False


def _get_connection():
    """Vrátí databázové připojení — SQLite nebo PostgreSQL."""
    if _je_supabase():
        import streamlit as st
        import psycopg2
        return psycopg2.connect(st.secrets["supabase"]["url"]), "pg"
    else:
        import sqlite3
        return sqlite3.connect("revize_elektro.db"), "sqlite"


# ─── Inicializace tabulky ─────────────────────────────────────────────────────

def init_db() -> None:
    """Vytvoří tabulku pokud neexistuje (funguje pro SQLite i PostgreSQL)."""
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        # PostgreSQL používá SERIAL místo AUTOINCREMENT
        if typ == "pg":
            cur.execute("""
                CREATE TABLE IF NOT EXISTS revize (
                    id                  SERIAL PRIMARY KEY,
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
        else:
            cur.execute("""
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
        con.commit()
    finally:
        con.close()


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def get_all() -> list[dict]:
    """Vrátí všechny revize seřazené podle data platnosti."""
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka, upozorneni_odeslano FROM revize ORDER BY datum_platnosti")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def pridat(data: dict) -> None:
    """Vloží novou revizi."""
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        if typ == "pg":
            cur.execute("""
                INSERT INTO revize (nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka)
                VALUES (%(nazev)s, %(umisteni)s, %(typ)s, %(datum_revize)s, %(datum_platnosti)s, %(revizni_technik)s, %(poznamka)s)
            """, data)
        else:
            cur.execute("""
                INSERT INTO revize (nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka)
                VALUES (:nazev, :umisteni, :typ, :datum_revize, :datum_platnosti, :revizni_technik, :poznamka)
            """, data)
        con.commit()
    finally:
        con.close()


def smazat(rid: int) -> None:
    """Smaže revizi podle ID."""
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM revize WHERE id = %s" if typ == "pg" else "DELETE FROM revize WHERE id = ?", (rid,))
        con.commit()
    finally:
        con.close()


def oznacit_odeslano(ids: list[int]) -> None:
    """Označí záznamy jako upozornění odesláno."""
    if not ids:
        return
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        if typ == "pg":
            cur.execute(
                f"UPDATE revize SET upozorneni_odeslano = 1 WHERE id = ANY(%s)",
                (ids,)
            )
        else:
            placeholders = ",".join("?" * len(ids))
            cur.execute(f"UPDATE revize SET upozorneni_odeslano = 1 WHERE id IN ({placeholders})", ids)
        con.commit()
    finally:
        con.close()


def reset_odeslano() -> None:
    """Resetuje příznak odeslaného upozornění u všech záznamů."""
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        cur.execute("UPDATE revize SET upozorneni_odeslano = 0")
        con.commit()
    finally:
        con.close()


def get_k_odeslani(days: int = 7) -> list[dict]:
    """Vrátí revize expirující do `days` dní u kterých nebylo odesláno upozornění."""
    limit = (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")
    con, typ = _get_connection()
    try:
        cur = con.cursor()
        placeholder = "%s" if typ == "pg" else "?"
        cur.execute(f"""
            SELECT id, nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka, upozorneni_odeslano
            FROM revize
            WHERE datum_platnosti <= {placeholder}
              AND upozorneni_odeslano = 0
            ORDER BY datum_platnosti
        """, (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


# ─── Pomocné funkce ───────────────────────────────────────────────────────────

def stav(datum_platnosti: str) -> tuple[str, str, int]:
    """
    Vrátí trojici (text_stavu, css_třída_badge, počet_zbývajících_dní).
    css_třída_badge: 'badge-red' | 'badge-orange' | 'badge-green'
    """
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
