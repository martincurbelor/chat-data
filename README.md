# Chat with your Data — Axion Energy

Chat conversacional con historial de ventas. El usuario hace preguntas en lenguaje natural y recibe respuestas con texto, tablas y gráficos generados en tiempo real.

---

## Arquitectura

```
Browser (GitHub Pages)
  └─ index.html + config.js
       │
       │ POST /chat {"question": "..."}
       ▼
  api.py (Flask · localhost:5000 / Tailscale 100.86.8.29:5000)
       │
       ├─ Paso 1: Claude genera SQL a partir de la pregunta
       ├─ Paso 2: Flask ejecuta el SQL en MySQL local (ventas_axion)
       └─ Paso 3: Claude interpreta los resultados y devuelve bloques JSON
                        │
                        ▼
              [{"type":"text",...}, {"type":"table",...}, {"type":"bar",...}]
```

---

## Archivos

| Archivo | Descripción |
|---|---|
| `api.py` | Backend Flask. Expone `/health` y `/chat`. Orquesta los 3 pasos. |
| `generate_historico.py` | Genera `docs/historico.json` con datos agregados (no usado por el chat, referencia histórica). |
| `start_api.bat` | Arranca la API manualmente desde Windows. |
| `instalar_servicio.bat` | Instala la API como servicio de Windows con NSSM (requiere admin). |
| `docs/index.html` | Frontend del chat. |
| `docs/config.js` | URL del backend (`window.API_URL`). Cambiar si cambia la IP Tailscale. |
| `docs/env.js` | API key de Anthropic (no versionado, excluido del repo). |

---

## Flujo de una pregunta

1. El usuario escribe una pregunta en el chat
2. `index.html` hace `POST /chat` al backend con la pregunta e historial reciente
3. `api.py` llama a Claude con el schema de `ventas_diarias` → Claude devuelve una query SQL
4. Flask ejecuta la query en MySQL (solo permite SELECT, máx 500 filas)
5. `api.py` llama a Claude de nuevo con la pregunta + resultados → Claude devuelve array de bloques
6. El frontend renderiza cada bloque según su tipo:
   - `text` → párrafo con markdown básico
   - `table` → tabla HTML con columnas tipadas
   - `bar` / `line` → gráfico Chart.js

---

## Configuración

**Backend** lee del `.env` en la raíz del proyecto:
```
DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
ANTHROPIC_API_KEY
```

**Frontend** apunta al backend via `docs/config.js`:
```js
window.API_URL = 'http://100.86.8.29:5000';  // IP Tailscale
```

---

## Operación

| Acción | Comando |
|---|---|
| Iniciar API (manual) | `start_api.bat` |
| Instalar como servicio | `instalar_servicio.bat` (como admin) |
| Detener servicio | `net stop AxionChatAPI` |
| Ver estado | `services.msc` → "Axion Chat with your Data API" |

El `generate_historico.py` se ejecuta automáticamente cada mañana como parte de `sync_ventas.py`.
