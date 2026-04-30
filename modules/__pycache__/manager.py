# ═══════════════════════════════════════════════════════════
#  modules/appdb/manager.py  –  Datenbank-Verwaltung
# ═══════════════════════════════════════════════════════════

import sqlite3
import csv
import io
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import config
from core.database import get_connection


def get_tables():
    """Gibt alle sichtbaren Tabellen mit Zeilenanzahl zurueck."""
    conn   = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    result = []
    for t in tables:
        name = t["name"]
        if name in config.APPDB_HIDDEN_TABLES:
            continue
        count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        result.append({"name": name, "rows": count})
    conn.close()
    return result


def get_table_data(table: str, limit=500, offset=0):
    """Gibt Spalten + Zeilen einer Tabelle zurueck."""
    # Sicherheit: nur erlaubte Tabellennamen
    conn   = get_connection()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if table not in tables:
        conn.close()
        return {"columns": [], "rows": [], "total": 0}

    total = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    rows  = conn.execute(
        f"SELECT * FROM [{table}] ORDER BY rowid DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()

    columns = [d[0] for d in rows[0].description] if rows else []
    conn.close()
    return {
        "columns": columns,
        "rows":    [list(r) for r in rows],
        "total":   total,
    }


def delete_row(table: str, row_id: int):
    conn   = get_connection()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if table not in tables:
        conn.close()
        return False
    conn.execute(f"DELETE FROM [{table}] WHERE id=?", (row_id,))
    conn.commit()
    conn.close()
    return True


def clear_table(table: str):
    conn   = get_connection()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if table not in tables:
        conn.close()
        return False
    conn.execute(f"DELETE FROM [{table}]")
    conn.commit()
    conn.close()
    return True


def export_csv(table: str) -> str:
    """Gibt den Tabelleninhalt als CSV-String zurueck."""
    data = get_table_data(table, limit=100000)
    out  = io.StringIO()
    w    = csv.writer(out)
    w.writerow(data["columns"])
    w.writerows(data["rows"])
    return out.getvalue()


def get_db_info():
    """Gibt allgemeine DB-Infos zurueck."""
    size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
    tables = get_tables()
    total_rows = sum(t["rows"] for t in tables)
    return {
        "path":       config.DB_PATH,
        "size_kb":    round(size / 1024, 1),
        "tables":     len(tables),
        "total_rows": total_rows,
    }
