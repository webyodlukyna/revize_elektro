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
import json


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
        con.execute("""
            CREATE TABLE IF NOT EXISTS revize_prilohy (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                revize_id   INTEGER NOT NULL,
                file_name   TEXT NOT NULL,
                file_path   TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                uploaded_by TEXT,
                FOREIGN KEY (revize_id) REFERENCES revize(id) ON DELETE CASCADE
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS revize_historie (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                revize_id     INTEGER NOT NULL,
                changed_at    TEXT NOT NULL,
                changed_by    TEXT,
                action        TEXT NOT NULL,
                snapshot_json TEXT,
                FOREIGN KEY (revize_id) REFERENCES revize(id) ON DELETE CASCADE
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_name  TEXT,
                action     TEXT NOT NULL,
                detail     TEXT
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


def update_revize(rid: int, data: dict) -> None:
    if _je_supabase():
        _supabase_client().table("revize").update(data).eq("id", rid).execute()
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute("""
            UPDATE revize
            SET nazev = :nazev,
                umisteni = :umisteni,
                typ = :typ,
                datum_revize = :datum_revize,
                datum_platnosti = :datum_platnosti,
                revizni_technik = :revizni_technik,
                poznamka = :poznamka
            WHERE id = :id
        """, {**data, "id": rid})


def get_prilohy(revize_id: int) -> list[dict]:
    if _je_supabase():
        try:
            res = (
                _supabase_client().table("revize_prilohy")
                .select("*")
                .eq("revize_id", revize_id)
                .order("uploaded_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM revize_prilohy WHERE revize_id = ? ORDER BY id DESC",
            (revize_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def uloz_prilohu(revize_id: int, file_name: str, file_path: str, uploaded_by: str = "uživatel") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if _je_supabase():
        try:
            _supabase_client().table("revize_prilohy").insert({
                "revize_id": revize_id,
                "file_name": file_name,
                "file_path": file_path,
                "uploaded_at": ts,
                "uploaded_by": uploaded_by,
            }).execute()
        except Exception:
            return
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute(
            """
            INSERT INTO revize_prilohy (revize_id, file_name, file_path, uploaded_at, uploaded_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (revize_id, file_name, file_path, ts, uploaded_by),
        )


def smazat_prilohu(priloha_id: int) -> None:
    if _je_supabase():
        try:
            _supabase_client().table("revize_prilohy").delete().eq("id", priloha_id).execute()
        except Exception:
            return
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute("DELETE FROM revize_prilohy WHERE id = ?", (priloha_id,))


def pridej_historii(revize_id: int, action: str, snapshot: dict, changed_by: str = "uživatel") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snapshot_json = json.dumps(snapshot, ensure_ascii=False)

    if _je_supabase():
        try:
            _supabase_client().table("revize_historie").insert({
                "revize_id": revize_id,
                "changed_at": ts,
                "changed_by": changed_by,
                "action": action,
                "snapshot_json": snapshot_json,
            }).execute()
        except Exception:
            return
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute(
            """
            INSERT INTO revize_historie (revize_id, changed_at, changed_by, action, snapshot_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (revize_id, ts, changed_by, action, snapshot_json),
        )


def get_historie(revize_id: int, limit: int = 200) -> list[dict]:
    if _je_supabase():
        try:
            res = (
                _supabase_client().table("revize_historie")
                .select("*")
                .eq("revize_id", revize_id)
                .order("changed_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM revize_historie WHERE revize_id = ? ORDER BY id DESC LIMIT ?",
            (revize_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def log_akce(action: str, detail: str = "", user_name: str = "uživatel") -> None:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if _je_supabase():
        try:
            _supabase_client().table("audit_log").insert({
                "created_at": created_at,
                "user_name": user_name,
                "action": action,
                "detail": detail,
            }).execute()
        except Exception:
            return
        return

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.execute(
            "INSERT INTO audit_log (created_at, user_name, action, detail) VALUES (?, ?, ?, ?)",
            (created_at, user_name, action, detail),
        )


def get_audit(limit: int = 200) -> list[dict]:
    if _je_supabase():
        try:
            res = (
                _supabase_client().table("audit_log")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    import sqlite3
    with sqlite3.connect("revize_elektro.db") as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
