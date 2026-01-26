# ---------------  app.py (Flask + Admin + PDF) ---------------
from flask import (
    Flask, render_template_string, request, redirect, url_for,
    send_from_directory, session, jsonify
)
import sqlite3, os
ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMG
from datetime import date
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2 import sql

# ---------- CONFIG GRATIS EN LA NUBE ----------
import os, psycopg2, cloudinary
from cloudinary.uploader import upload as cld_upload
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
RENDER = os.getenv("RENDER") == "true"
if RENDER:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET")
    )

# ---------- ÚNICA INSTANCIA DE FLASK ----------
app = Flask(__name__)
app.secret_key = "clave_secreta_niquee"

# ---------- API JSON (PostgreSQL) ----------
@app.route('/api/registro_rapido', methods=['POST'])
def api_registro_rapido():
    from datetime import date
    data = request.get_json(force=True)
    nombre = data.get('nombre')
    cedula = data.get('cedula')
    anio   = data.get('anio')

    if not all([nombre, cedula, anio]):
        return jsonify({"error": "Faltan campos"}), 400

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO jugadores (nombre, cedula, anio_nacimiento, posicion, goles, asistencias, fecha_ingreso) "
            "VALUES (%s, %s, %s, 'POR', 0, 0, %s) RETURNING id",
            (nombre, cedula, anio, date.today().isoformat())
        )
        nuevo_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"id": nuevo_id, "nombre": nombre}), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({"error": "Cédula ya registrada"}), 409
    finally:
        conn.close()

# ---------- CONFIG DE CARPETAS ----------
UPLOAD_IMG = os.path.join(os.getcwd(), "static", "uploads")
UPLOAD_DOCS = os.path.join(os.getcwd(), "static", "uploads", "docs")
os.makedirs(UPLOAD_IMG, exist_ok=True)
os.makedirs(UPLOAD_DOCS, exist_ok=True)

ADMIN_PASSWORD = "jeremias123"
PDF_PASSWORD = "niquee123"
FORM_PASSWORD = "guthler123"

# … resto de tus rutas …

# ---------- BD ----------
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jugadores (
                id SERIAL PRIMARY KEY,
                nombre TEXT,
                cedula TEXT UNIQUE,
                anio_nacimiento INTEGER,
                posicion TEXT,
                goles INTEGER,
                asistencias INTEGER,
                imagen TEXT,
                fecha_ingreso TEXT,
                pdf_url TEXT
            )
        """)
        cur.execute(""" 
            CREATE TABLE IF NOT EXISTS inscripciones (
                id SERIAL PRIMARY KEY,
                jugador_id INTEGER REFERENCES jugadores(id),
                cedula TEXT,
                anio_nacimiento INTEGER,
                torneo TEXT,
                estado TEXT DEFAULT 'PENDIENTE',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
      
        # ✅ Columna nueva para URL de Cloudinary
        cur.execute("""
            ALTER TABLE jugadores
            ADD COLUMN IF NOT EXISTS pdf_url TEXT;
        """)
        # ✅ Tabla de aprobaciones
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lecciones_aprobadas (
                id SERIAL PRIMARY KEY,
                jugador_id INTEGER REFERENCES jugadores(id) ON DELETE CASCADE,
                leccion_numero INTEGER CHECK (leccion_numero BETWEEN 1 AND 10),
                nota INTEGER CHECK (nota BETWEEN 0 AND 10),
                fecha_aprobado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (jugador_id, leccion_numero)
            );
        """)
    # <-- aquí termina el WITH
    conn.commit()
    conn.close()     

@app.route("/admin/panel")
def admin_panel():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, cedula, anio_nacimiento, posicion, goles, asistencias, imagen, pdf_url FROM jugadores ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return render_template_string(ADMIN_PANEL_HTML, jugadores=rows)
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        else:
            return "❌ Contraseña incorrecta"
    return render_template_string(ADMIN_LOGIN_HTML)
    
# ---------- GUARDAR APROBACIÓN (PostgreSQL) ----------
@app.route("/guardar_aprobacion_pg", methods=["POST"])
def guardar_aprobacion_pg():
    data = request.get_json(force=True)          # ← permite JSON sin Content-Type explícito
    jugador_id = data.get("jugador_id")
    leccion_numero = data.get("leccion_numero")
    nota = data.get("nota")

    # Validación rápida
    if not all([jugador_id, leccion_numero, nota]):
        return {"status": "error", "msg": "Faltan campos"}, 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO lecciones_aprobadas (jugador_id, leccion_numero, nota)
            VALUES (%s, %s, %s)
            ON CONFLICT (jugador_id, leccion_numero)
            DO UPDATE SET nota = EXCLUDED.nota,
                          fecha_aprobado = NOW()
            """,
            (jugador_id, leccion_numero, nota)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        app.logger.exception("Error al guardar aprobación")  # ← traza completa en logs
        return {"status": "error", "msg": str(e)}, 500
    finally:
        conn.close()

    return {"status": "ok"}, 200


@app.route("/subir_pdf/<int:jugador_id>", methods=["POST"])
def subir_pdf(jugador_id):
    # 1. sólo admin puede subir
    if not session.get("admin"):
        return "❌ Acceso denegado", 403

    file = request.files.get("pdf")
    if not file or file.filename == "":
        return "Archivo no válido", 400
    if not file.filename.lower().endswith(".pdf"):
        return "Solo se permite PDF", 400

    # 2. tamaño máximo 10 MB
    if request.content_length and request.content_length > 10 * 1024 * 1024:
        return "PDF demasiado grande (máx 10 MB)", 413

    # 3. subida a Cloudinary
    resultado = cld_upload(
        file,
        resource_type='raw',
        folder=f"jugadores/{jugador_id}",
        public_id=f"doc-{int(datetime.now().timestamp())}"
    )
    pdf_url = resultado['secure_url']

    # 4. guardar URL en PostgreSQL
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jugadores SET pdf_url = %s WHERE id = %s",
        (pdf_url, jugador_id)
    )
    conn.commit()
    conn.close()

    # 5. mismo redireccionamiento original
    return redirect(url_for("index"))
   
# ---------- API: lista de jugadores para autocompletar ----------
@app.route("/api/jugadores")
def api_jugadores():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, cedula FROM jugadores ORDER BY nombre")
    rows = cursor.fetchall()
    conn.close()
    return {"jugadores": [{"id": r[0], "nombre": r[1], "cedula": r[2]} for r in rows]}

# ---------- API: guardar inscripción ----------
@app.route("/api/inscripciones", methods=["POST"])
def api_inscripciones():
    data = request.get_json()
    jugador_id = data.get("jugador_id")
    cedula     = data.get("cedula")
    anio       = data.get("anio")
    torneo     = data.get("torneo")
    if not all([jugador_id, cedula, anio, torneo]):
        return {"message": "Faltan datos"}, 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inscripciones (jugador_id, cedula, anio_nacimiento, torneo, estado) VALUES (%s, %s, %s, %s, 'PENDIENTE')",
        (jugador_id, cedula, anio, torneo)
    )
    conn.commit()
    conn.close()
    return {"message": "Inscripción registrada. realiza el pago para confirmar participación."}
@app.route("/uploads/<path:name>")
def serve_img(name):
    if RENDER:
        return redirect(name)
    else:
        return send_from_directory(UPLOAD_IMG, name)

@app.route('/docs/<name>')
def serve_pdf(name):
    if not session.get("admin"):
        return "❌ Acceso denegado", 403

    safe_name = secure_filename(name)          # ← elimina ../, etc.
    if RENDER:
        return redirect(name)
    return send_from_directory(UPLOAD_DOCS, safe_name)
 
@app.route("/borrar/<int:jugador_id>", methods=["POST"])
def borrar(jugador_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # 1. Borrar inscripciones que dependen de este jugador
    cursor.execute("DELETE FROM inscripciones WHERE jugador_id = %s", (jugador_id,))

    # 2. Ahora sí borrar al jugador
    cursor.execute("DELETE FROM jugadores WHERE id = %s", (jugador_id,))

    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

# ---------- HTML ----------
INDEX_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>⚽ NIQUÉE FÚTBOL CLUB</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{
      font-family:Segoe UI,system-ui,sans-serif;
      background:url("{{ url_for('static', filename='uploads/fondo.jpg') }}") no-repeat center center fixed;
      background-size:cover;
      color:#ffff00;
      font-size:16px;
      line-height:1.5;
    }
    h1{text-align:center;padding:20px 0 12px;font-size:2rem;color:#00ff00}
    .ventana{
      background:#1b263b;
      border-radius:12px;
      padding:20px;
      margin:20px auto;
      max-width:1000px;
      color:#ffff00;
    }
    .ventana h2{text-align:center;margin-bottom:15px}
    .galeria{
      display:grid;
      grid-template-columns:repeat(4,1fr);
      gap:15px;
    }
    .galeria img{
      width:100%;
      height:140px;
      object-fit:cover;
      border-radius:8px;
    }
    .botones{
      display:flex;
      justify-content:center;
      gap:15px;
      margin-bottom:10px;
      flex-wrap:wrap;
    }
    .btn{
      background:#415a77;
      color:#ffff00;
      padding:10px 18px;
      border:none;
      border-radius:8px;
      cursor:pointer;
      font-size:15px;
      text-decoration:none;
    }
    .btn:hover{background:#5a7fb0}
    .jugador{
      display:flex;
      align-items:center;
      gap:12px;
      margin-bottom:12px;
      background:#415a77;
      padding:10px;
      border-radius:8px;
    }
    .jugador img{
      width:60px;
      height:60px;
      object-fit:cover;
      border-radius:50%;
    }
    .info{font-size:14px}
    .info strong{display:block;margin-bottom:4px}
    footer{
      text-align:center;
      padding:15px 10px;
      font-size:13px;
      background:#09101a;
      color:#ffff80;
    }
    @media(max-width:900px){
      .galeria{grid-template-columns:repeat(2,1fr)}
    }
    .modal{
      display:none;
      position:fixed;
      top:10%;left:50%;
      transform:translateX(-50%);
      z-index:9999;
      max-width:480px;
      width:90%;
    }
  </style>
</head>
<body>

  <!-- VENTANA 1: Título + Galería -->
  <div class="ventana">
    <h1>⚽ NIQUÉE FÚTBOL CLUB</h1>
    <div class="galeria">
      <img src="{{ url_for('static', filename='uploads/niquenegro.jpg') }}" alt="Equipo 1">
      <img src="{{ url_for('static', filename='uploads/logo.png') }}" alt="Equipo 2">
      <img src="{{ url_for('static', filename='uploads/gruponique.jpg') }}" alt="Equipo 3">
      <img src="{{ url_for('static', filename='uploads/niqueazul.jpg') }}" alt="Equipo 4">
    </div>
  </div>

  <!-- VENTANA 2: Botones principales -->
  <div class="ventana">
    <div class="botones">
      <a href="/admin" class="btn">Panel Admin</a>
      <button class="btn" onclick="document.getElementById('infoModal').style.display='block'">+ Info</button>
      <button class="btn" onclick="pedirClavePDF()">Cargar PDF</button>
      <button class="btn" onclick="abrirModal()">Formulario</button>
    </div>
    <!-- Entrada para módulos -->
    <div style="margin-top:15px;text-align:center">
      <input type="text" id="cedulaTest" placeholder="Ingresa tu cédula" maxlength="20" style="padding:6px;width:200px;">
      <button class="btn btn-sm btn-success" onclick="buscarYAbrirTest()">Módulos</button>
    </div>
  </div>

  <!-- VENTANA 3: Plantilla de Jugadores -->
  <div class="ventana">
    <h2>Plantilla de Jugadores</h2>
    {% for j in jugadores %}
      <div class="jugador">
        <img src="{% if j[7] %}{{ j[7] }}{% else %}#{% endif %}" alt="Foto">
        <div class="info">
          <strong>{{ j[1]|e }}</strong>
          <span>{{ j[2]|e }} • {{ j[3]|e }}</span>
          <span>G:{{ j[4] }} • A:{{ j[5] }}</span>
          {% if j[7] %}
            <a href="{{ j[7] }}" download="{{ j[1] | replace(' ', '_') }}_acta.pdf" style="color:#ffff80;font-size:13px;">📄 Descargar PDF</a>
          {% else %}
            <span style="font-size:12px;color:#aaa;">Sin PDF</span>
          {% endif %}
        </div>
      </div>
    {% endfor %}
  </div>

  <!-- ========== MODALES (fuera del flujo normal) ========== -->
  <!-- Modal Info -->
  <div id="infoModal" class="ventana modal">
    <span style="float:right;cursor:pointer;" onclick="this.parentElement.style.display='none'">&times;</span>
    <h3>Información del Club</h3>
    <p>
      Niquee Fútbol Club nació en 2017 en Guayaquil con la filosofía de adoración a Dios, juego limpio y trabajo en equipo.
      Participamos en ligas barriales y torneos locales. ¡Buscamos talento, honestidad y lealtad!<br>
      Entrenamientos: lun/mié/vie 18:00-20:00 | Cancha: sintéticas fútbol Garzota samanes<br>
      Redes: <a href="https://www.facebook.com/share/1CWH1PEHMU/" target="_blank" style="color:#ffff80">Facebook</a>
    </p>
  </div>

  <!-- Modal PDF -->
<div id="pdfModal" class="ventana modal">
  <span style="float:right;cursor:pointer;" onclick="this.parentElement.style.display='none'">&times;</span>
  <h3>Subir acta PDF del jugador</h3>
  <form id="pdfForm" enctype="multipart/form-data">
    <label>Seleccione jugador:</label>
    <select id="pdfJugador" required>
      {% for j in jugadores %}
        <option value="{{ j[0] }}">{{ j[1] }}</option>
      {% endfor %}
    </select>

    <label>Archivo PDF (máx 10 MB):</label>
    <input type="file" name="pdf" accept=".pdf" required>

    <button type="submit" class="btn">Subir PDF</button>
  </form>
</div>

  <!-- Modal Inscripción -->
  <div id="modalInscripcion" class="ventana modal">
    <span style="float:right;cursor:pointer;" onclick="cerrarModal()">&times;</span>
    <h3>Formulario de Inscripción</h3>
    <form id="formInscripcion" onsubmit="guardarInscripcion(event)">
      <label>Nombres completos:</label>
      <input type="text" id="nombres" list="listaJugadores" placeholder="Escribe para ver jugadores" required autocomplete="off">
      <label>Cédula de ciudadanía:</label>
      <input type="text" id="cedula" pattern="[0-9]+" maxlength="20" placeholder="Ingrese su cédula" required>
      <datalist id="listaJugadores"></datalist>
      <label>Año de nacimiento:</label>
      <input type="number" id="anio" min="1900" max="2100" required>
      <label>Torneo:</label>
      <select id="torneo" required>
        <option value="">-- Seleccione --</option>
        <option>Liga Futbol Fest</option>
        <option>Liga Internacional World Cup 2026</option>
        <option>Liga Samanes</option>
        <option>Liga Miraflores</option>
        <option>Liga Mucho Lote</option>
        <option>Duran Amateur League</option>
        <option>Otros</option>
      </select>
      <button type="submit" class="btn" style="width:100%;margin-top:15px;">Registrar</button>
    </form>
  </div>

  <!-- ========== FOOTER ========== -->
  <footer>
    @transguthler&asociados • fonos 593-958787986 / 593-992123592<br>
    cguthler@hotmail.com •
    <a href="https://www.facebook.com/share/1CWH1PEHMU/" target="_blank" style="color:#ffff80">Facebook</a><br>
    Guayaquil – Ecuador
  </footer>

  <script>
    const PDF_CLAVE_CORRECTA = "{{ PDF_PASSWORD }}";
    const FORM_CLAVE_CORRECTA = "{{ FORM_PASSWORD }}";

    function pedirClavePDF() {
      const intro = prompt("Introduce la contraseña para cargar PDF:");
      if (intro === PDF_CLAVE_CORRECTA) {
        document.getElementById('pdfModal').style.display = 'block';
      } else if (intro !== null) {
        alert("\u274C Contraseña incorrecta");
      }
    }

    document.getElementById('pdfForm').addEventListener('submit', function (e) {
      e.preventDefault();
      const id = document.getElementById('pdfJugador').value;
      const file = this.pdf.files[0];
      if (!file) return;

      const fd = new FormData();
      fd.append('pdf', file);
      fetch('/subir_pdf/' + encodeURIComponent(id), {
        method: 'POST',
        body: fd
      })
      .then(() => location.reload())
      .catch(() => alert('Error al subir'));
    });

    /* ---------- MODAL INSCRIPCIÓN ---------- */
    let jugadoresList = []; // [{id, nombre}, ...]

    /* Cargar jugadores al iniciar */
    (async () => {
      try {
        const res = await fetch('/api/jugadores');
        const data = await res.json();
        jugadoresList = data.jugadores;
        const datalist = document.getElementById('listaJugadores');
        jugadoresList.forEach(j => {
          const opt = document.createElement('option');
          opt.value = j.nombre;
          datalist.appendChild(opt);
        });
      } catch (e) {
        console.error('No se pudieron cargar jugadores', e);
      }
    })();

   function abrirModal() {
  const clave = prompt("Contraseña de administrador para inscripciones:");
  if (clave === FORM_CLAVE_CORRECTA) {
    document.getElementById('modalInscripcion').style.display = 'block';
  } else if (clave !== null) {
    alert("❌ Contraseña incorrecta");
  }
}
    function cerrarModal() {
      document.getElementById('modalInscripcion').style.display = 'none';
      document.getElementById('formInscripcion').reset();
    }

    async function guardarInscripcion(e) {
      e.preventDefault();
      const nombre = document.getElementById('nombres').value.trim();
      const jugador = jugadoresList.find(j => j.nombre === nombre);
      if (!jugador) {
        alert('Seleccione un jugador de la lista.');
        return;
      }
      const payload = {
        jugador_id: jugador.id,
        cedula: document.getElementById('cedula').value.trim(),
        anio: document.getElementById('anio').value,
        torneo: document.getElementById('torneo').value
      };
      const r = await fetch('/api/inscripciones', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const res = await r.json();
      alert(res.message);
      cerrarModal();
    }
    /* ---------- GUARDAR APROBACIÓN (TEST) ---------- */
async function finalizar() {
  const total = preguntas.length;
  if (aciertos === total) {
    localStorage.setItem("modulo1", "aprobado");

    // Usa el ID real del jugador que escribió su cédula
    const jugadorId = window.jugadorIdReal || 1;

      fetch("/guardar_aprobacion_pg", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
  jugador_id: window.jugadorIdReal || 1,
  leccion_numero: 1,
  nota: aciertos
})  
    });

    document.getElementById('resultArea').innerHTML =
      `<div class="alert alert-success">¡Aprobaste! Estás listo para jugar tu partido.</div>`;

    const btnSiguiente = document.createElement('button');
    btnSiguiente.className = 'btn btn-success mt-3';
    btnSiguiente.textContent = 'Ver siguiente lección →';
    btnSiguiente.onclick = () => abrirLeccionDentro(2);
    document.getElementById('resultArea').appendChild(btnSiguiente);
  } else {
    document.getElementById('resultArea').innerHTML =
      `<div class="alert alert-warning">Respondiste ${aciertos}/${total}. Necesitas 10/10 para aprobar.</div>`;
    setTimeout(() => volverAlModal(), 3000);
  }
}

/* ---------- FUNCIÓN NUEVA: BUSCAR Y ABRIR TEST ---------- */
async function buscarYAbrirTest() {
  const cedula = document.getElementById('cedulaTest').value.trim();
  if (!cedula) { alert("Ingresa tu cédula"); return; }

  const res = await fetch('/api/jugadores');
  const data = await res.json();
  const jugador = data.jugadores.find(j => j.cedula === cedula);

  if (!jugador) { alert("No estás registrado. Regístrate primero."); return; }

  window.jugadorIdReal = jugador.id;
  abrirLeccionDentro(1); // ✅ ABRE LECCIÓN 1
}
/* ---------- VALIDACIÓN SUBIDA PDF ---------- */
document.getElementById('pdfForm').addEventListener('submit', function (e) {
  e.preventDefault();
  const file = this.pdf.files[0];
  if (!file) { alert("Selecciona un archivo."); return; }
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
    alert("Solo se permite PDF.");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    alert("El archivo no puede superar 10 MB.");
    return;
  }

  const id = document.getElementById('pdfJugador').value;
  const fd = new FormData();
  fd.append('pdf', file);
  fetch('/subir_pdf/' + encodeURIComponent(id), {
    method: 'POST',
    body: fd,
    credentials: 'include'
  })
  .then(() => location.reload())
  .catch(() => alert('Error al subir'));
});

  </script>

  <!-- Modal Inscripción -->
  <div id="modalInscripcion" class="ventana" style="display:none; position:fixed; top:10%; left:50%; transform:translateX(-50%); z-index:9999; max-width:480px; width:90%;">
    <span style="float:right;cursor:pointer;" onclick="cerrarModal()">&times;</span>
  
 <h3>Formulario de Inscripción</h3>
<form id="formInscripcion" onsubmit="guardarInscripcion(event)">
  <label>Nombres completos:</label>
  <input type="text" id="nombres" list="listaJugadores" placeholder="Escribe para ver jugadores" required autocomplete="off">
  
  <label>Cédula de ciudadanía:</label>
  <input type="text" id="cedula" pattern="[0-9]+" maxlength="20" placeholder="Ingrese su cédula" required>
  <datalist id="listaJugadores"></datalist>

  <label>Año de nacimiento:</label>
  <input type="number" id="anio" min="1900" max="2100" required>

  <label>Torneo:</label>
  <select id="torneo" required>
    <option value="">-- Seleccione --</option>
    <option>Liga Futbol Fest</option>
    <option>Liga Internacional World Cup 2026</option>
    <option>Liga Samanes</option>
    <option>Liga Miraflores</option>
    <option>Liga Mucho Lote</option>
    <option>Duran Amateur League</option>
    <option>Otros</option>
  </select>

  <button type="submit" class="btn" style="width:100%; margin-top:15px;">Registrar</button>
</form> </div>
</div>   <!-- cierra modalInscripcion -->

<!-- Modal Módulo -->
<div id="moduloModal" class="ventana modulo-lecciones" style="display:none;position:fixed;top:10%;left:50%;transform:translateX(-50%);z-index:9999;max-width:800px;width:90%;"></div>
<script>
const PASS_MODULO = "futbol2025";

function abrirModulo(){
  const modal = document.getElementById('moduloModal');
  modal.innerHTML = `
    <div class="modal-content">
      <span class="close" onclick="modal.style.display='none'">&times;</span>
      <h3>Lecciones del Módulo</h3>
      <div class="list-group">
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(1); return false;">Lección 1: Fundamentos y reglas</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(2); return false;">Lección 2: Pase interior</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(3); return false;">Lección 3: Conducción</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(4); return false;">Lección 4: Control orientado</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(5); return false;">Lección 5: Presión tras pérdida</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(6); return false;">Lección 6: Saque de banda</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(7); return false;">Lección 7: Corner a favor</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(8); return false;">Lección 8: Corner en contra</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(9); return false;">Lección 9: Posesión y descanso</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(10); return false;">Lección 10: Fair Play y actitud</a>
      </div>
      <button class="btn btn-sm btn-secondary mt-3" onclick="location.reload()">Cerrar</button>
    </div>`;
  modal.style.display = 'block';
}
function abrirLeccionDentro(n){
  fetch("/leccion/" + n)
    .then(r => r.text())
    .then(html => {
      const modal = document.getElementById('moduloModal');
      modal.innerHTML = html;

      /* =====  EJECUTAR SCRIPTS INSERTADOS  ===== */
      modal.querySelectorAll('script').forEach(oldScript => {
        const newScript = document.createElement('script');
        Array.from(oldScript.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
      });

      modal.style.display = 'block';
      modal.scrollTop = 0;
    });
}

function volverAlModal(){
  location.reload();
}

/* ---------- MODAL CENTRADO Y SCROLLEABLE ---------- */
function abrirModulo(){
  /* si ya existe solo lo mostramos */
  let overlay = document.getElementById('overlayModulos');
  if(!overlay){
    overlay = document.createElement('div');
    overlay.id = 'overlayModulos';
    overlay.style.cssText = `
      position:fixed; inset:0;                  /* tapa toda la pantalla */
      background:rgba(0,0,0,.75);               /* fondo oscuro */
      display:flex; align-items:center; justify-content:center;
      z-index:9999;
    `;
    overlay.innerHTML = `
      <div style="
        background:#1b263b; color:#ffff00; border-radius:12px; padding:25px 30px;
        max-width:480px; width:90%; max-height:80vh; overflow-y:auto;
        box-shadow:0 8px 30px rgba(0,0,0,.6);
      ">
        <span style="float:right;cursor:pointer;" onclick="cerrarModulo()">&times;</span>
        <h3>Lecciones del Módulo</h3>
        <div class="list-group" style="margin-top:15px;">
          ${[...Array(10)].map((_,i)=>`
            <a href="#" class="list-group-item" onclick="abrirLeccionDentro(${i+1}); return false;">
              Lección ${i+1}: ${['Fundamentos y reglas','Pase interior','Conducción','Control orientado','Presión tras pérdida','Saque de banda','Corner a favor','Corner en contra','Posesión y descanso','Fair Play y actitud'][i]}
            </a>`).join('')}
        </div>
        <button class="btn btn-sm btn-secondary mt-3" onclick="cerrarModulo()">Cerrar</button>
      </div>
    `;
    document.body.appendChild(overlay);
    overlay.addEventListener('click',e=>{ if(e.target===overlay) cerrarModulo(); });
    document.addEventListener('keydown',e=>{ if(e.key==='Escape') cerrarModulo(); });
  }
  overlay.style.display = 'flex';
}

function cerrarModulo(){
  const m = document.getElementById('overlayModulos');
  if(m) m.style.display = 'none';
}

function volverAlModal(){
  location.reload();
}
</script>
</body>
</html>
"""
ADMIN_LOGIN_HTML = """
<form method="post" style="max-width:300px;margin:auto">
  <h2>Admin Login</h2>
  <input type="password" name="password" placeholder="Contraseña" style="width:100%;padding:8px">
  <button type="submit" style="width:100%;margin-top:10px">Entrar</button>
</form>
"""  

ADMIN_PANEL_HTML = """
<h2>Panel Admin</h2>
<a href="/">Ver vista pública</a>
<form method="post" action="/guardar" enctype="multipart/form-data">
  <label>Nombre completo</label><input name="nombre" required>
  <label>Cédula:</label>
<input type="text" name="cedula" pattern="[0-9]+" maxlength="20" placeholder="Cédula del jugador" required>
  <label>Año de nacimiento</label><input type="number" name="anio_nacimiento" required>
  <label>Posición</label><input name="posicion" required>
  <label>Goles</label><input type="number" name="goles" required>
  <label>Asistencias</label><input type="number" name="asistencias" required>
  <label>Foto</label><input type="file" name="imagen" accept="image/*">
  <button type="submit">Guardar Jugador</button>
</form>
<hr>

{% for j in jugadores %}
<div style="margin-bottom:8px;">
  <strong>{{ j[1] }}</strong> |
  <span>C.I. {{ j[2] }}</span> |
  <a href="{{ j[7] }}" target="_blank">📄 Ver PDF</a>

  <!-- EDITAR -->
  <form action="/editar/{{ j[0] }}" method="GET" style="display:inline">
    <button type="submit" style="background:none;border:none;color:blue;cursor:pointer;">✏️ Editar</button>
  </form>

  <!-- BORRAR -->
  <form action="/borrar/{{ j[0] }}" method="POST" style="display:inline" onsubmit="return confirm('¿Borrar?')">
    <button type="submit" style="background:none;border:none;color:red;cursor:pointer;">🗑 Borrar</button>
  </form>
</div>
{% endfor %}
"""   

@app.route("/")
def index():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
    "SELECT id, nombre, cedula, anio_nacimiento, posicion, goles, asistencias, imagen, pdf_url FROM jugadores ORDER BY id DESC"
)
    jugadores = cursor.fetchall()
    conn.close()
    return render_template_string(INDEX_HTML, jugadores=jugadores, PDF_PASSWORD=PDF_PASSWORD, FORM_PASSWORD=FORM_PASSWORD)

# ---------- VERIFICAR APROBACIONES ----------
@app.route("/ver_lecciones")
def ver_lecciones():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
SELECT j.nombre, l.leccion_numero, l.fecha_aprobado, l.nota
FROM lecciones_aprobadas l
JOIN jugadores j ON j.id = l.jugador_id
ORDER BY l.fecha_aprobado DESC
""")
    rows = cursor.fetchall()
    conn.close()

    html = "<h2>Lecciones Aprobadas</h2><table border='1' cellpadding='6'>"
    html += "<tr><th>Jugador</th><th>Lección</th><th>Fecha</th><th>Nota</th></tr>"
    for row in rows:
        html += f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}/10</td></tr>"
    html += "</table>"
    return html
    
# ---------- GUARDAR APROBACIÓN (Aiven) ----------
@app.route("/guardar_aprobacion", methods=["POST"])
def guardar_aprobacion():
    data = request.get_json()
    jugador_id = data.get("jugador_id")
    leccion_numero = data.get("leccion_numero")
    nota = data.get("nota")

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO lecciones_aprobadas (jugador_id, leccion_numero, nota)
            VALUES (%s, %s, %s)
            ON CONFLICT (jugador_id, leccion_numero)
            DO UPDATE SET nota = EXCLUDED.nota,
                          fecha_aprobado = NOW()
            """,
            (jugador_id, leccion_numero, nota)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"status": "error", "msg": str(e)}, 500
    finally:
        conn.close()

    return {"status": "ok"}, 200
    
 # ---------- SERVIR CUALQUIER LECCIÓN ----------
@app.route('/leccion/<int:n>')
def leccion(n):
    try:
        with open(f'templates/leccion{n}.html', 'r', encoding='utf-8') as f:
            return render_template_string(f.read())
    except FileNotFoundError:
        return "Lección no encontrada", 404   

# ---------- VER DATOS CRUDOS (solo admin) ----------
@app.route("/ver_datos")
def ver_datos():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. jugadores
    cur.execute("SELECT id, nombre, anio_nacimiento, posicion, imagen FROM jugadores ORDER BY id DESC LIMIT 10")
    jugadores = cur.fetchall()

    # 2. inscripciones
    cur.execute("SELECT i.id, j.nombre, i.cedula, i.torneo, i.estado, i.fecha "
                "FROM inscripciones i JOIN jugadores j ON j.id = i.jugador_id "
                "ORDER BY i.fecha DESC LIMIT 10")
    inscripciones = cur.fetchall()

    # 3. lecciones aprobadas
    cur.execute("SELECT j.nombre, l.leccion_numero, l.nota, l.fecha_aprobado "
                "FROM lecciones_aprobadas l JOIN jugadores j ON j.id = l.jugador_id "
                "ORDER BY l.fecha_aprobado DESC LIMIT 10")
    lecciones = cur.fetchall()

    conn.close()

    html = "<h2>Jugadores (top 10)</h2><ul>"
    for j in jugadores:
       html += f"<li>ID {j[0]} – {j[1]} – Año {j[2]} – Pos {j[3]} – Img: {j[4] or 'Sin imagen'}</li>"
    html += "</ul><h2>Inscripciones (top 10)</h2><ul>"
    for i in inscripciones:
        html += f"<li>ID {i[0]} – {i[1]} – CI {i[2]} – Torneo {i[3]} – Estado {i[4]} – {i[5]}</li>"
    html += "</ul><h2>Lecciones aprobadas (top 10)</h2><ul>"
    for l in lecciones:
        html += f"<li>{l[0]} – Lección {l[1]} – Nota {l[2]}/10 – {l[3]}</li>"
    html += "</ul><a href='/admin/panel'>← Volver</a>"
    return html

def asegurar_columnas():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        columnas = [
            ("posicion", "TEXT"),
            ("goles", "INTEGER"),
            ("asistencias", "INTEGER"),
            ("imagen", "TEXT"),
            ("fecha_ingreso", "TEXT"),
            ("pdf_url", "TEXT")
        ]
        for col, tipo in columnas:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='jugadores' AND column_name=%s",
                (col,)
            )
            if not cur.fetchone():
                cur.execute(
                    sql.SQL("ALTER TABLE jugadores ADD COLUMN {} {}")
                    .format(sql.Identifier(col), sql.SQL(tipo))
                )
                print(f"✅ Columna '{col}' creada.")
    conn.commit()
    conn.close()

from datetime import date   # ← agrega esta línea arriba del todo si no la tienes

@app.route("/guardar", methods=["POST"])
def guardar():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    nombre   = request.form["nombre"]
    cedula   = request.form["cedula"]
    anio     = request.form["anio_nacimiento"]
    posicion = request.form["posicion"]
    goles    = int(request.form["goles"])
    asist    = int(request.form["asistencias"])
    file     = request.files.get("imagen")

    imagen_url = None
    if file and allowed_file(file.filename):
        # Opción rápita: subida local
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_IMG, filename)
        file.save(file_path)
        imagen_url = url_for('serve_img', name=filename)

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jugadores (nombre, cedula, anio_nacimiento, posicion, goles, asistencias, imagen, fecha_ingreso) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (nombre, cedula, anio, posicion, goles, asist, imagen_url, date.today().isoformat())
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

# -------------------------------------------------
# Ejecutar una sola vez al arrancar la aplicación
# -------------------------------------------------
init_db()
asegurar_columnas()

# ---------- RUTA EDITAR ----------
@app.route("/editar/<int:jugador_id>", methods=["GET", "POST"])
def editar(jugador_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    if request.method == "POST":
        nombre   = request.form["nombre"]
        cedula   = request.form["cedula"]
        anio     = request.form["anio_nacimiento"]
        posicion = request.form["posicion"]
        goles    = int(request.form["goles"])
        asist    = int(request.form["asistencias"])
        file     = request.files.get("imagen")

        if file and allowed_file(file.filename):
            resultado = cld_upload(
                file,
                folder=f"jugadores/{cedula}",
                public_id=f"img-{int(datetime.now().timestamp())}",
                resource_type='image'
            )
            imagen_url = resultado['secure_url']
            cursor.execute(
                "UPDATE jugadores SET nombre=%s, cedula=%s, anio_nacimiento=%s, posicion=%s, goles=%s, asistencias=%s, imagen=%s WHERE id=%s",
                (nombre, cedula, anio, posicion, goles, asist, imagen_url, jugador_id)
            )
        else:
            cursor.execute(
                "UPDATE jugadores SET nombre=%s, cedula=%s, anio_nacimiento=%s, posicion=%s, goles=%s, asistencias=%s WHERE id=%s",
                (nombre, cedula, anio, posicion, goles, asist, jugador_id)
            )
        conn.commit()
        conn.close()
        return redirect(url_for("admin_panel"))

    # GET → mostramos formulario con datos actuales
    cursor.execute(
        "SELECT id, nombre, cedula, anio_nacimiento, posicion, goles, asistencias, imagen, pdf_url FROM jugadores WHERE id = %s",
        (jugador_id,)
    )
    jugador = cursor.fetchone()
    conn.close()
    return render_template_string(EDITAR_HTML, j=jugador)

# ---------- TEMPLATE EDITAR ----------
EDITAR_HTML = """
<h2>Editar Jugador</h2>
<a href="/admin/panel">← Volver al panel</a>
<form method="post" enctype="multipart/form-data">
  <input type="hidden" name="id" value="{{ j[0] }}">
  <label>Nombre completo</label><input name="nombre" value="{{ j[1] }}" required>
  <label>Cédula</label><input name="cedula" value="{{ j[2] }}" pattern="[0-9]+" maxlength="20" required>
  <label>Año nacimiento</label><input type="number" name="anio_nacimiento" value="{{ j[3] }}" required>
  <label>Posición</label><input name="posicion" value="{{ j[4] }}" required>
  <label>Goles</label><input type="number" name="goles" value="{{ j[5] }}" required>
  <label>Asistencias</label><input type="number" name="asistencias" value="{{ j[6] }}" required>
  <label>Nueva foto (opcional)</label><input type="file" name="imagen" accept="image/*">
  <button type="submit">Guardar cambios</button>
</form>
"""

# ---------- INFORME: JUGADORES QUE COMPLETARON LAS 6 LECCIONES ----------
@app.route("/reporte_lecciones_completas")
def reporte_lecciones_completas():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Solo jugadores con 6 lecciones aprobadas (nota 10)
    cursor.execute("""
        SELECT j.id, j.nombre, j.cedula, COUNT(l.leccion_numero) as lecciones_ok
        FROM jugadores j
        JOIN lecciones_aprobadas l ON l.jugador_id = j.id
        WHERE l.nota = 10
        GROUP BY j.id, j.nombre, j.cedula
        HAVING COUNT(l.leccion_numero) = 6
        ORDER BY j.nombre
    """)# ... tus rutas anteriores ...


# ---------- VERIFICAR APROBACIONES (debug) ----------
@app.route("/ver_lecciones")
def ver_lecciones():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT j.nombre, l.leccion_numero, l.fecha_aprobado, l.nota
        FROM lecciones_aprobadas l
        JOIN jugadores j ON j.id = l.jugador_id
        ORDER BY l.fecha_aprobado DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    html = "<h2>Lecciones Aprobadas</h2><table border='1' cellpadding='6'>"
    html += "<tr><th>Jugador</th><th>Lección</th><th>Fecha</th><th>Nota</th></tr>"
    for row in rows:
        html += f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}/10</td></tr>"
    html += "</table>"
    return html


# ---------- GUARDAR APROBACIÓN (Aiven) ----------
@app.route("/guardar_aprobacion", methods=["POST"])
def guardar_aprobacion():
    ... (lo que ya tenías)
    jugadores = cursor.fetchall()
    conn.close()

    html = f"""
    <h2>Jugadores que completaron las 6 lecciones (10/10)</h2>
    <p>Total: {len(jugadores)}</p>
    <table border='1' cellpadding='6'>
      <tr><th>ID</th><th>Nombre</th><th>Cédula</th><th>Lecciones aprobadas</th></tr>
    """
    for j in jugadores:
        html += f"<tr><td>{j[0]}</td><td>{j[1]}</td><td>{j[2]}</td><td>{j[3]}</td></tr>"
    html += "</table><br><a href='/admin/panel'>← Volver al panel</a>"
    return html


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))