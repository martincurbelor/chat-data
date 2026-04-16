"""
generate_historico.py — Chat with your Data
Genera docs/historico.json con datos agregados de ventas_diarias (año actual + anterior)
Se integra en sync_ventas.py para actualizarse diariamente.
"""

import os
import json
import mysql.connector
from datetime import datetime, date
from decimal import Decimal
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "docs", "historico.json")

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "ventas_axion"),
}

class Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal): return float(o)
        if isinstance(o, (date, datetime)): return str(o)
        return super().default(o)


def fetch(conn, sql, params=None):
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    return cur.fetchall()


def build_historico(conn):
    anio_actual = datetime.today().year
    anios = [anio_actual - 1, anio_actual]

    # ── Resumen diario ────────────────────────────────────────────────────────
    rows = fetch(conn, """
        SELECT
            DATE(fecha)       AS fecha,
            YEAR(DATE(fecha)) AS anio,
            SUM(CASE WHEN TRIM(UPPER(categoria)) = 'COMBUSTIBLE' THEN importe ELSE 0 END) AS combustible,
            SUM(CASE WHEN TRIM(UPPER(categoria)) != 'COMBUSTIBLE' THEN importe ELSE 0 END) AS mini,
            SUM(importe)                  AS total,
            COUNT(DISTINCT nro_ticket)    AS transacciones
        FROM ventas_diarias
        WHERE YEAR(DATE(fecha)) IN (%s, %s)
        GROUP BY DATE(fecha), YEAR(DATE(fecha))
        ORDER BY fecha
    """, anios)

    resumen_diario = [
        {
            "fecha":         str(r["fecha"]),
            "anio":          r["anio"],
            "combustible":   round(float(r["combustible"]), 2),
            "mini":          round(float(r["mini"]), 2),
            "total":         round(float(r["total"]), 2),
            "transacciones": r["transacciones"],
        }
        for r in rows
    ]

    # ── Resumen mensual ───────────────────────────────────────────────────────
    rows = fetch(conn, """
        SELECT
            YEAR(DATE(fecha))  AS anio,
            MONTH(DATE(fecha)) AS mes,
            SUM(CASE WHEN TRIM(UPPER(categoria)) = 'COMBUSTIBLE' THEN importe ELSE 0 END) AS combustible,
            SUM(CASE WHEN TRIM(UPPER(categoria)) != 'COMBUSTIBLE' THEN importe ELSE 0 END) AS mini,
            SUM(importe)                        AS total,
            COUNT(DISTINCT nro_ticket)          AS transacciones,
            COUNT(DISTINCT DATE(fecha))         AS dias_con_venta
        FROM ventas_diarias
        WHERE YEAR(DATE(fecha)) IN (%s, %s)
        GROUP BY YEAR(DATE(fecha)), MONTH(DATE(fecha))
        ORDER BY anio, mes
    """, anios)

    resumen_mensual = []
    for r in rows:
        tx = r["transacciones"] or 1
        resumen_mensual.append({
            "anio":           r["anio"],
            "mes":            r["mes"],
            "combustible":    round(float(r["combustible"]), 2),
            "mini":           round(float(r["mini"]), 2),
            "total":          round(float(r["total"]), 2),
            "transacciones":  tx,
            "dias_con_venta": r["dias_con_venta"],
            "ticket_promedio": round(float(r["total"]) / tx, 2),
        })

    # ── Top productos ─────────────────────────────────────────────────────────
    rows = fetch(conn, """
        SELECT
            producto,
            TRIM(UPPER(categoria))  AS categoria,
            YEAR(DATE(fecha))       AS anio,
            SUM(importe)            AS total,
            SUM(cantidad)           AS cantidad
        FROM ventas_diarias
        WHERE YEAR(DATE(fecha)) IN (%s, %s)
        GROUP BY producto, TRIM(UPPER(categoria)), YEAR(DATE(fecha))
        ORDER BY total DESC
    """, anios)

    productos_map = defaultdict(lambda: {"categoria": "", "por_anio": {}})
    for r in rows:
        p = r["producto"]
        productos_map[p]["categoria"] = r["categoria"]
        productos_map[p]["por_anio"][r["anio"]] = {
            "total":    round(float(r["total"]), 2),
            "cantidad": round(float(r["cantidad"]), 2),
        }

    top_productos = sorted(
        [{"producto": k, **v} for k, v in productos_map.items()],
        key=lambda x: sum(a["total"] for a in x["por_anio"].values()),
        reverse=True
    )[:50]

    # ── Por categoría ─────────────────────────────────────────────────────────
    rows = fetch(conn, """
        SELECT
            TRIM(UPPER(categoria))     AS categoria,
            YEAR(DATE(fecha))          AS anio,
            SUM(importe)               AS total,
            COUNT(DISTINCT nro_ticket) AS transacciones
        FROM ventas_diarias
        WHERE YEAR(DATE(fecha)) IN (%s, %s)
        GROUP BY TRIM(UPPER(categoria)), YEAR(DATE(fecha))
        ORDER BY total DESC
    """, anios)

    cat_map = defaultdict(lambda: {"por_anio": {}})
    for r in rows:
        cat_map[r["categoria"]]["por_anio"][r["anio"]] = {
            "total":         round(float(r["total"]), 2),
            "transacciones": r["transacciones"],
        }
    por_categoria = [{"categoria": k, **v} for k, v in cat_map.items()]

    # ── Distribución horaria ──────────────────────────────────────────────────
    rows = fetch(conn, """
        SELECT
            HOUR(hora)                 AS hora,
            YEAR(DATE(fecha))          AS anio,
            SUM(importe)               AS total,
            COUNT(DISTINCT nro_ticket) AS transacciones
        FROM ventas_diarias
        WHERE YEAR(DATE(fecha)) IN (%s, %s) AND hora IS NOT NULL
        GROUP BY HOUR(hora), YEAR(DATE(fecha))
        ORDER BY hora
    """, anios)

    hora_map = defaultdict(lambda: {"por_anio": {}})
    for r in rows:
        hora_map[r["hora"]]["por_anio"][r["anio"]] = {
            "total":         round(float(r["total"]), 2),
            "transacciones": r["transacciones"],
        }
    por_hora = [{"hora": k, **v} for k, v in sorted(hora_map.items())]

    # ── Ticket stats ──────────────────────────────────────────────────────────
    rows = fetch(conn, """
        SELECT
            YEAR(DATE(fecha))               AS anio,
            SUM(importe)                    AS total,
            COUNT(DISTINCT nro_ticket)      AS transacciones,
            MAX(importe)                    AS max_ticket,
            MIN(DATE(fecha))                AS desde,
            MAX(DATE(fecha))                AS hasta
        FROM ventas_diarias
        WHERE YEAR(DATE(fecha)) IN (%s, %s)
        GROUP BY YEAR(DATE(fecha))
    """, anios)

    ticket_stats = {}
    for r in rows:
        tx = r["transacciones"] or 1
        ticket_stats[r["anio"]] = {
            "total":           round(float(r["total"]), 2),
            "transacciones":   tx,
            "ticket_promedio": round(float(r["total"]) / tx, 2),
            "max_ticket":      round(float(r["max_ticket"]), 2),
            "desde":           str(r["desde"]),
            "hasta":           str(r["hasta"]),
        }

    return {
        "generado":       datetime.now().isoformat(),
        "anios":          anios,
        "resumen_diario":  resumen_diario,
        "resumen_mensual": resumen_mensual,
        "top_productos":   top_productos,
        "por_categoria":   por_categoria,
        "por_hora":        por_hora,
        "ticket_stats":    ticket_stats,
    }


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        data = build_historico(conn)
    finally:
        conn.close()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, cls=Encoder, ensure_ascii=False)

    print(f"[OK] historico.json generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
