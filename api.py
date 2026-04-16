"""
api.py — Chat with your Data · Backend Flask
Recibe preguntas en lenguaje natural, genera SQL con Claude, ejecuta en MySQL,
interpreta resultados y devuelve bloques renderizables (texto/tabla/grafico).

Iniciar: python api.py
Puerto:  5000
"""

import os
import json
import re
import anthropic
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = Flask(__name__)
CORS(app)  # permite requests desde GitHub Pages

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "ventas_axion"),
}

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

SCHEMA = """
Tabla: ventas_diarias
Columnas:
  id              INT           — clave primaria
  fecha           DATETIME      — fecha y hora de la transaccion (usar DATE(fecha) para filtrar por dia)
  nro_ticket      VARCHAR       — numero de ticket/boleta
  producto        VARCHAR       — nombre del producto
  categoria       VARCHAR       — categoria del producto (ej: 'COMBUSTIBLE', 'BEBIDAS (BASICO)', etc.)
  cantidad        DECIMAL       — unidades vendidas
  precio_unitario DECIMAL       — precio por unidad en $U
  importe         DECIMAL       — total de la linea (cantidad * precio_unitario) en $U
  hora            TIME          — hora de la transaccion (puede ser NULL)
  load_date       DATETIME      — fecha de carga del registro

Notas importantes:
- Los montos estan en pesos uruguayos ($U)
- COMBUSTIBLE se identifica con: TRIM(UPPER(categoria)) = 'COMBUSTIBLE'
- Para filtrar por hora usa HOUR(hora) o hora BETWEEN 'HH:MM:SS' AND 'HH:MM:SS'
- Para filtrar por dia usa DATE(fecha) = 'YYYY-MM-DD'
- Para filtrar por mes usa YEAR(DATE(fecha)) y MONTH(DATE(fecha))
- nro_ticket identifica una transaccion completa (puede tener muchas lineas/productos)
- Los datos cubren 2025 y 2026
"""

SYSTEM_SQL = f"""Sos un experto en SQL y analista de datos para Axion Energy (estacion de servicio + minimercado en Uruguay).
Dada una pregunta en lenguaje natural, genera UNA SOLA consulta SQL valida para MySQL.

{SCHEMA}

Reglas:
- Responde SOLO con la query SQL, sin explicaciones, sin ```sql, sin nada mas
- Solo SELECT, nunca INSERT/UPDATE/DELETE/DROP
- Usa alias descriptivos en espanol para las columnas
- Limita los resultados a 500 filas maximas con LIMIT 500
- Para productos usa LIKE con % para busquedas parciales (ej: producto LIKE '%COCA%')
- Agrupa cuando tenga sentido para no devolver filas repetidas
- Siempre ordena los resultados de forma logica (fecha ASC, total DESC, etc.)
"""

SYSTEM_INTERPRET = """Sos un analista de datos para Axion Energy que interpreta resultados de consultas SQL.
Los montos estan en pesos uruguayos ($U). Usa punto como separador de miles.

Responde SIEMPRE con un array JSON de bloques. Formatos disponibles:

Texto:    {"type":"text","content":"texto, podés usar **negrita**"}
Tabla:    {"type":"table","title":"Titulo","columns":["Col1","Col2"],"rows":[["v1","v2"]],"col_types":["text","num"]}
          (col_types: "text", "num", "pos", "neg")
Barras:   {"type":"bar","title":"Titulo","labels":["Ene","Feb"],"datasets":[{"label":"Serie","data":[1,2],"color":"#4f8ef7"}]}
Lineas:   {"type":"line","title":"Titulo","labels":["Ene","Feb"],"datasets":[{"label":"Serie","data":[1,2],"color":"#4f8ef7"}]}

Reglas:
- Responde SOLO con el array JSON, sin texto antes ni despues, sin ```
- Combina bloques: texto con analisis + tabla o grafico si aplica
- Para series temporales usa grafico de lineas
- Para comparativas categoricas usa barras
- Formatea montos como "$U 1.234.567"
- Si los resultados estan vacios, explicalo claramente
"""


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def run_sql(query):
    """Ejecuta la query y devuelve (columns, rows). Solo permite SELECT."""
    clean = query.strip().lstrip(";")
    if not re.match(r"^\s*SELECT\b", clean, re.IGNORECASE):
        raise ValueError("Solo se permiten consultas SELECT")

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(clean)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        return columns, rows
    finally:
        conn.close()


def call_claude(system, messages):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    body     = request.get_json(force=True)
    question = body.get("question", "").strip()
    history  = body.get("history", [])

    if not question:
        return jsonify({"error": "Pregunta vacia"}), 400

    # ── Paso 1: generar SQL ────────────────────────────────────────────────
    sql_messages = []
    for h in history[-4:]:
        if h.get("role") in ("user", "assistant"):
            sql_messages.append({"role": h["role"], "content": h["content"]})
    sql_messages.append({"role": "user", "content": question})

    try:
        sql_query = call_claude(SYSTEM_SQL, sql_messages).strip()
        # limpiar posibles bloques ```sql ... ```
        sql_query = re.sub(r"```(?:sql)?", "", sql_query, flags=re.IGNORECASE).strip().strip("`")
    except Exception as e:
        return jsonify({"error": f"Error generando SQL: {e}"}), 500

    # ── Paso 2: ejecutar SQL ───────────────────────────────────────────────
    try:
        columns, rows = run_sql(sql_query)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({
            "error": f"Error ejecutando SQL: {e}",
            "sql":   sql_query,
        }), 500

    # ── Paso 3: interpretar resultados ────────────────────────────────────
    result_text = json.dumps(
        {"columns": columns, "rows": rows[:500]},
        ensure_ascii=False,
        default=str,
    )

    interpret_prompt = f"""Pregunta del usuario: {question}

SQL ejecutado:
{sql_query}

Resultados ({len(rows)} filas):
{result_text}"""

    try:
        raw = call_claude(SYSTEM_INTERPRET, [{"role": "user", "content": interpret_prompt}])
        blocks = json.loads(raw)
    except json.JSONDecodeError:
        blocks = [{"type": "text", "content": raw}]
    except Exception as e:
        return jsonify({"error": f"Error interpretando resultados: {e}"}), 500

    return jsonify({
        "blocks": blocks,
        "sql":    sql_query,
        "rows":   len(rows),
    })


if __name__ == "__main__":
    print("Chat with your Data API corriendo en http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
