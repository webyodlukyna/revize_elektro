"""
database.py – Veškerá práce s SQLite databází
"""

import sqlite3
from datetime import date, datetime

DB_PATH = "revize_elektro.db"


def init_db() -> None:
    """Vytvoří databázi a tabulku, pokud ještě neexistují."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS revize (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                nazev                 TEXT    NOT NULL,
                umisteni              TEXT,
                typ                   TEXT,
                datum_revize          TEXT    NOT NULL,
                datum_platnosti       TEXT    NOT NULL,
                revizni_technik       TEXT,
                poznamka              TEXT,
                upozorneni_odeslano   INTEGER DEFAULT 0
            )
        """)


def get_all() -> list[dict]:
    """Vrátí všechny revize seřazené podle data platnosti."""
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM revize ORDER BY datum_platnosti"
        ).fetchall()
    return [dict(r) for r in rows]


def pridat(data: dict) -> None:
    """Vloží novou revizi. Klíče slovníku odpovídají sloupcům tabulky."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            INSERT INTO revize
                (nazev, umisteni, typ, datum_revize, datum_platnosti, revizni_technik, poznamka)
            VALUES
                (:nazev, :umisteni, :typ, :datum_revize, :datum_platnosti, :revizni_technik, :poznamka)
            """,
            data,
        )


def smazat(rid: int) -> None:
    """Smaže revizi podle ID."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM revize WHERE id = ?", (rid,))


def oznacit_odeslano(ids: list[int]) -> None:
    """Označí záznamy jako 'upozornění odesláno'."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            f"UPDATE revize SET upozorneni_odeslano = 1 WHERE id IN ({placeholders})",
            ids,
        )


def reset_odeslano() -> None:
    """Resetuje příznak odeslaného upozornění u všech záznamů."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE revize SET upozorneni_odeslano = 0")


def get_k_odeslani(days: int = 7) -> list[dict]:
    """
    Vrátí revize, jejichž platnost vyprší do `days` dní
    a upozornění ještě nebylo odesláno.
    """
    limit = (date.today() + __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT * FROM revize
            WHERE datum_platnosti <= ?
              AND upozorneni_odeslano = 0
            ORDER BY datum_platnosti
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Pomocné funkce ───────────────────────────────────────────────────────────

def stav(datum_platnosti: str) -> tuple[str, str, int]:
    """
    Vrátí trojici (text_stavu, css_třída_badge, počet_zbývajících_dní).
    css_třída_badge: 'badge-red' | 'badge-orange' | 'badge-green'
    """
    plat   = datetime.strptime(datum_platnosti, "%Y-%m-%d").date()
    zbyvá  = (plat - date.today()).days

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
