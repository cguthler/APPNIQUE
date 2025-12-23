# ---------------  app.py (Flask + Admin + PDF) ---------------
from flask import (
    Flask, render_template_string, request, redirect, url_for,
    send_from_directory, session, jsonify
)
import sqlite3, os
from datetime import date
from werkzeug.utils import secure_filename

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

# ---------- CREAR TABLAS ----------
with sqlite3.connect('futbol.db') as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jugadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cedula TEXT UNIQUE NOT NULL,
            anio_nacimiento INTEGER
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aprobaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jugador_id INTEGER,
            leccion_numero INTEGER,
            nota INTEGER,
            fecha TEXT,
            FOREIGN KEY(jugador_id) REFERENCES jugadores(id)
        );
    """)
    conn.commit()

# ---------- API JSON ----------
@app.route('/api/registro_rapido', methods=['POST'])
def api_registro_rapido():
    data = request.get_json(force=True)
    nombre = data.get('nombre')
    cedula = data.get('cedula')
    anio   = data.get('anio')
    if not all([nombre, cedula, anio]):
        return jsonify({"error": "Faltan campos"}), 400
    conn = sqlite3.connect('futbol.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO jugadores (nombre, cedula, anio_nacimiento) VALUES (?,?,?)",
                (nombre, cedula, anio))
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return jsonify({"id": nuevo_id})


@app.route('/guardar_aprobacion', methods=['POST'])
def api_guardar_aprobacion():
    data = request.get_json(force=True)
    jugador_id   = data.get('jugador_id')
    leccion_num  = data.get('leccion_numero')
    nota         = data.get('nota')
    if not all([jugador_id, leccion_num, nota]):
        return jsonify({"error": "Faltan campos"}), 400
    conn = sqlite3.connect('futbol.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO aprobaciones (jugador_id, leccion_numero, nota, fecha) VALUES (?,?,?,?)",
                (jugador_id, leccion_num, nota, date.today().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- CONFIG DE CARPETAS ----------
UPLOAD_IMG = "static/uploads"
UPLOAD_DOCS = "static/uploads/docs"
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
                anio_nacimiento INTEGER,
                posicion TEXT,
                goles INTEGER,
                asistencias INTEGER,
                imagen TEXT,
                fecha_ingreso TEXT,
                pdf TEXT
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

        conn.commit()
    conn.close()

@app.route("/admin/panel")
def admin_panel():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, anio_nacimiento, posicion, goles, asistencias, imagen, pdf_url FROM jugadores ORDER BY id DESC"
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

@app.route("/guardar", methods=["POST"])
def guardar():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    nombre = request.form["nombre"]
    anio = request.form["anio_nacimiento"]
    posicion = request.form["posicion"]
    goles = request.form["goles"]
    asistencias = request.form["asistencias"]

    imagen = ""
    if "imagen" in request.files:
        file = request.files["imagen"]
        if file.filename != "":
            if RENDER:
                upload_res = cld_upload(file)
                imagen = upload_res['secure_url']
            else:
                filename = secure_filename(file.filename)
                path = os.path.join(UPLOAD_IMG, filename)
                file.save(path)
                imagen = filename

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jugadores (nombre, anio_nacimiento, posicion, goles, asistencias, imagen) VALUES (%s, %s, %s, %s, %s, %s)",
        (nombre, int(anio), posicion, int(goles), int(asistencias), imagen)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("admin_panel"))
    
@app.route("/subir_pdf/<int:jugador_id>", methods=["POST"])
def subir_pdf(jugador_id):
    file = request.files.get("pdf")
    if not file or file.filename == "":
        return "Archivo no válido", 400
    if not file.filename.lower().endswith(".pdf"):
        return "Solo se permite PDF", 400

    # Subimos a Cloudinary en carpeta privada por jugador
    resultado = cld_upload(
        file,
        resource_type='raw',
        folder=f"jugadores/{jugador_id}",
        public_id=f"doc-{int(datetime.now().timestamp())}"
    )
    pdf_url = resultado['secure_url']

    # Guardamos la URL en el jugador correspondiente
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jugadores SET pdf_url = %s WHERE id = %s",
        (pdf_url, jugador_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index"))
   
# ---------- API: lista de jugadores para autocompletar ----------
@app.route("/api/jugadores")
def api_jugadores():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM jugadores ORDER BY nombre")
    rows = cursor.fetchall()
    conn.close()
    return {"jugadores": [{"id": r[0], "nombre": r[1]} for r in rows]}

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
        return "❌ Acceso denegado"
    if RENDER:
        return redirect(name)
    else:
        return send_from_directory(UPLOAD_DOCS, name)

@app.route("/borrar/<int:jugador_id>")
def borrar(jugador_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
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
  <title>&#9917; NIQU&#201;E FUTBOL CLUB</title>
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
    h1 {
      text-align:center;
      padding:20px 0 12px;
      font-size:2rem;
      color:#00ff00;
    } 
    .ventana{
      background:#1b263b;
      border-radius:12px;
      padding:20px;
      margin:20px auto;
      max-width:1000px;
      color:#ffff00;
    }
    .ventana h2{
      text-align:center;
      margin-bottom:15px;
    }
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
    .modulo-lecciones{
  background: #f5f5f5; /* fondo claro */
  color: #1b263b;      /* texto oscuro que resalta */
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 12px rgba(0,0,0,.25);
}
  </style>
</head>
<body>

  <!-- VENTANA 1: Título + Galería -->
  <div class="ventana">
    <h1>&#9917; NIQUEE FÚTBOL CLUB</h1>
    <div class="galeria">
      <img src="{{ url_for('static', filename='uploads/niqueeblanco.jpg') }}" alt="Equipo 1">
      <img src="{{ url_for('static', filename='uploads/logo.png') }}" alt="Equipo 2">
      <img src="{{ url_for('static', filename='uploads/gruponique.jpg') }}" alt="Equipo 3">
      <img src="{{ url_for('static', filename='uploads/niqueazul.jpg') }}" alt="Equipo 4">
    </div>
  </div>

  <!-- VENTANA 2: Botones -->
  <div class="ventana">
    <div class="botones">
      <a href="/admin" class="btn">Panel Admin</a>
      <button class="btn" onclick="document.getElementById('infoModal').style.display='block'">+ Info</button>
      <button class="btn" onclick="pedirClavePDF()">Cargar PDF</button>
      <button class="btn" onclick="abrirModal()">Formulario</button>
      <button class="btn" onclick="if(document.getElementById('moduloModal'))abrirModulo();else alert('Modal no listo');">Módulo</button>
    </div>
  </div>

  <!-- VENTANA 3: Plantilla -->
  <div class="ventana">
    <h2>Plantilla de Jugadores</h2>
    {% for j in jugadores %}
      <div class="jugador">
        <img src="{{ url_for('serve_img', name=j[6]) }}" alt="Foto">
        <div class="info">
          <strong>{{ j[1] }}</strong>
          <span>{{ j[2] }} • {{ j[3] }}</span>
          <span>G:{{ j[4] }} • A:{{ j[5] }}</span>
          {% if j[7] %}
            <a href="{{ j[7] }}" download="{{ j[1] | replace(' ', '_') }}_acta.pdf" style="color:#ffff80;font-size:13px;">&#128196; Descargar PDF</a>
          {% else %}
            <span style="font-size:12px;color:#aaa;">Sin PDF</span>
          {% endif %}
        </div>
      </div>
    {% endfor %}
  </div>

  <!-- MODALES -->
  <div id="infoModal" class="ventana" style="display:none;position:fixed;top:20%;left:50%;transform:translateX(-50%);z-index:999;">
    <span style="float:right;cursor:pointer;" onclick="document.getElementById('infoModal').style.display='none'">&times;</span>
    <h3>Información del Club</h3>
    <p>
      Niquee Fútbol Club nació en 2017 en Guayaquil con la filosofía de adoración a Dios, juego limpio y trabajo en equipo.
      Participamos en ligas barriales y torneos locales. ¡Buscamos talento honestidad y lealtad!<br>
      Entrenamientos: lun/mié/vie 18:00-20:00 | Cancha: sintéticas fútbol Garzota samanes<br>
      Redes: <a href="https://www.facebook.com/share/1CWH1PEHMU/ " target="_blank" style="color:#ffff80">Facebook</a>
    </p>
  </div>

  <div id="pdfModal" class="ventana" style="display:none;position:fixed;top:20%;left:50%;transform:translateX(-50%);z-index:999;">
    <span style="float:right;cursor:pointer;" onclick="document.getElementById('pdfModal').style.display='none'">&times;</span>
    <h3>Subir PDF de jugador</h3>
    <form id="pdfForm" enctype="multipart/form-data">
      <label>Seleccione jugador:</label>
      <select id="pdfJugador" required>
        {% for j in jugadores %}
          <option value="{{ j[0] }}">{{ j[1] }}</option>
        {% endfor %}
      </select>
      <label>Archivo PDF:</label>
      <input type="file" name="pdf" accept=".pdf" required>
      <button type="submit" class="btn">Subir PDF</button>
    </form>
  </div>

  <footer>
    @transguthler&amp;asociados • fonos 593958787986-593992123592<br>
    cguthler@hotmail.com • <a href="https://www.facebook.com/share/1CWH1PEHMU/ " target="_blank" style="color:#ffff80">fb.me/share/1CWH1PEHMU</a><br>
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
  </script>

  <!-- Modal Inscripción -->
  <div id="modalInscripcion" class="ventana" style="display:none; position:fixed; top:10%; left:50%; transform:translateX(-50%); z-index:9999; max-width:480px; width:90%;">
    <span style="float:right;cursor:pointer;" onclick="cerrarModal()">&times;</span>
    <h3>Formulario de Inscripción</h3>
    <form id="formInscripcion" onsubmit="guardarInscripcion(event)">
      <label>Nombres completos:</label>
      <input type="text" id="nombres" list="listaJugadores" placeholder="Escribe para ver jugadores" required autocomplete="off">
      <datalist id="listaJugadores"></datalist>

      <label>Cédula de ciudadanía:</label>
      <input type="text" id="cedula" pattern="\d+" title="Solo números" required>

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
      </select><button type="submit" class="btn" style="width:100%; margin-top:15px;">Registrar</button>
  </form>
  </div>
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
        <a href="/leccion/1" target="_blank" class="list-group-item">Lección 1: Fundamentos y reglas</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(2)">Lección 2: Pase interior</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(3)">Lección 3: Conducción</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(4)">Lección 4: Control orientado</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(5)">Lección 5: Presión tras pérdida</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(6)">Lección 6: Saque de banda</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(7)">Lección 7: Corner a favor</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(8)">Lección 8: Corner en contra</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(9)">Lección 9: Posesión y descanso</a>
        <a href="#" class="list-group-item" onclick="abrirLeccionDentro(10)">Lección 10: Fair Play y actitud</a>
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
      modal.style.display = 'block';
      modal.scrollTop = 0;
    });
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
  <label>Año de nacimiento</label><input type="number" name="anio_nacimiento" required>
  <label>Posición</label><input name="posicion" required>
  <label>Goles</label><input type="number" name="goles" required>
  <label>Asistencias</label><input type="number" name="asistencias" required>
  <label>Foto</label><input type="file" name="imagen" accept="image/*">
  <button type="submit">Guardar Jugador</button>
</form>
<hr>
{% for j in jugadores %}
  <div>
    <strong>{{ j[1] }}</strong> |
    <a href="{{ j[7] }}" target="_blank">&#128196; Ver PDF</a>
    <a href="/borrar/{{ j[0] }}" onclick="return confirm('¿Borrar?')">&#128465; Borrar</a>
  </div>
{% endfor %}
"""
@app.route("/")
def index():
    init_db()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, anio_nacimiento, posicion, goles, asistencias, imagen, pdf_url FROM jugadores ORDER BY id DESC"
    )
    jugadores = cursor.fetchall()
    conn.close()
    return render_template_string(INDEX_HTML, jugadores=jugadores, PDF_PASSWORD=PDF_PASSWORD, FORM_PASSWORD=FORM_PASSWORD)

# ---------- LECCIÓN 1 ----------
LECCION_1_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Lección 1 - Fundamentos y reglas</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body{background:#1b263b;color:#ffffff;font-family:Segoe UI,system-ui,sans-serif}
    .ventana{background:#1b263b;border-radius:12px;padding:20px;color:#ffff00}
    .btn-leer{background:#415a77;color:#ffff00;border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:15px}
    .btn-leer:hover{background:#5a7fb0}
  </style><style>
  /* ===== MODAL-LECCIÓN ===== */
  #moduloModal{
    max-height:80vh;          /* altura máxima 80 % de la pantalla */
    overflow-y:auto;          /* scroll vertical si el contenido es largo */
    padding:20px;             /* separación interna */
    box-sizing:border-box;
  }
  .modal-content{
    background:#1b263b;
    color:#ffff00;
    border-radius:12px;
    padding:25px;
  }
  .timer-bar{ width:100%; height:6px; background:#eee; margin-bottom:8px; }
  .timer-fill{ height:100%; background:#0d6efd; transition:width 1s linear; }
  /* test */
  #testArea{ margin-top:15px; }
  #resultArea{ margin-top:10px; }
</style>
  
</head>
<body class="p-4">
  <!-- Botón volver -->
  <button onclick="volverAlModal()" class="btn btn-sm btn-secondary mb-3">← Volver al módulo</button>

  <div class="ventana" style="max-width:700px;margin:auto">
    <h4>Lección 1: Fundamentos y reglas del fútbol</h4>
    <div class="mt-3 p-3 bg-dark rounded small">
      <p>
        Listos para el partido esperado, el árbitro coloca el balón sobre el círculo central y pita el inicio. Cada jugador entiende que:<br>
        Primero, <strong>la mano</strong>: solo el portero puede usarla y solo dentro del rectángulo. Cualquier otro contacto es falta inmediata y, en el área, penal.<br>
        Segundo, <strong>el offside</strong>: si al recibir estás más cerca del arco que el último defensa, el banderín levanta y la jugada muere.<br>
        Tercero, <strong>el saque de banda</strong>: dos pies en el campo, balón detrás de la cabeza; si uno se adelanta o la tira mal, pierdes el saque.<br><br>

        Con las reglas claras, llegan los <strong>fundamentos</strong>:<br>
        - Controlar con el interior del pie o pisarla, no con el empeine, para que la pelota se detenga junto al pie y no tres metros adelante.<br>
        - Pasar con el interior, tobillo firme, al pie bueno del compañero: reduce un toque y evita el rebote.<br>
        - Disparar mirando al portero, no pensar al que dirán, y apuntar al poste cercano.<br>
        - En defensa, marcar de costado, brazo extendido, sin derribar.<br>
        - Desmarcarse antes de pedir: dos pasos al espacio y una señal con la mano bastan para romper líneas sin offside.<br>
        - En saques laterales, destinarla al jugador delante nuestro más cercano, llamándole la atención.<br><br>

        Las <strong>mañas</strong> permiten ganar segundos:<br>
        - Provocar que el balón golpee en las piernas del rival para ganar corners o laterales.<br>
        - Sacar rápido de banda mientras el otro discute.<br>
        - Descansar con la pelota dirigiendo el juego hacia el portero nuestro para tomar aliento y volver a empezar.<br><br>

        Pero aparecen los <strong>errores típicos del juego amateur</strong>:<br>
        - Protestar cada pitazo: amarilla gratuita, reclamarse entre nosotros muestra un equipo nervioso.<br>
        - Correr todos tras la pelota: se cierra el campo y desaparecen los pases.<br>
        - Pedirla estático: el defensa ya te tapa y perdés en la primera.<br>
        - Quedarse mirando la jugada: el rival contraataca y te coge parado en ventaja.<br>
        - Olvidan volver después de una buena jugada, no marcar hombre a hombre en saques laterales rivales y tiros de esquina.<br>
        - Salir desde el área por el centro no es recomendable, <strong>SALGA POR LOS LATERALES O A LA RAYA</strong>.<br><br>

        Cuando el árbitro pita el final, el equipo que supo conjugar reglas, fundamentos y pequeñas dosis de profesionalismo se lleva los tres puntos y la satisfacción de haber jugado al fútbol sin sobresaltos ni reclamos.
      </p>
    </div>

 <!-- Botón para desplegar el test -->
<div class="text-center mt-4">
  <button class="btn-leer" onclick="mostrarTest()">Leído → Comenzar test</button>
</div>

<!-- Aquí se insertará el test más tarde -->
<div id="testArea"></div>
<div id="resultArea" class="mt-3"></div>

<script>
/* ==========  FUNCIONES GLOBALES  ========== */
function volverAlModal() {
  location.reload();
}

function corregir(){
  const sel = document.querySelector('input[name="opt"]:checked');
  if(!sel){ alert("Elegí una opción."); return; }
  clearInterval(timer);
  if(parseInt(sel.value) === preguntas[idx].ok) aciertos++;
  idx++;
  if(idx < 10){ mostrarPregunta(); } else { finalizar(); }
}

function finalizar(){
  const total = preguntas.length;
  if(aciertos === total){
    localStorage.setItem("modulo1","aprobado");
    document.getElementById('resultArea').innerHTML =
      `<div class="alert alert-success">¡Aprobaste! Estás listo para jugar tu partido.</div>`;
    fetch("/guardar_aprobacion", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({jugador_id:1, leccion_numero:1, nota:aciertos})
    });
    const btn = document.createElement('button');
    btn.className = 'btn btn-success mt-3';
    btn.textContent = 'Ver siguiente lección →';
    btn.onclick = () => abrirLeccionDentro(2);
    document.getElementById('resultArea').appendChild(btn);
  }else{
    document.getElementById('resultArea').innerHTML =
      `<div class="alert alert-warning">Respondiste ${aciertos}/${total}. Necesitas 10/10 para aprobar.</div>`;
    setTimeout(()=> volverAlModal(), 3000);
  }
}

/* ==========  TEST  ========== */
function mostrarTest() {
  // Oculta el botón
  document.querySelector('.btn-leer').style.display = 'none';

  const TIME_PER_Q = 12;
  const preguntas = [
    {q:"¿Quién puede usar las manos dentro del rectángulo?",opts:["Cualquier jugador","Solo el portero","El capitán","Nadie"],ok:1},
    {q:"¿Qué ocurre si estás más cerca del arco que el último defensa al recibir un pase?",opts:["Gol válido","Falta directa","Offside","Saque de meta"],ok:2},
    {q:"¿Cómo se debe realizar el saque de banda?",opts:["Con un pie en la línea","Saltando","Dos pies en el campo y pelota detrás de la cabeza","Con la mano"],ok:2},
    {q:"¿Dónde se cobra un penal?",opts:["Desde el círculo central","Desde el punto penal","Desde la banda","Desde el corner"],ok:1},
    {q:"¿Con qué parte del pie se recomienda controlar un balón alto?",opts:["Empeine","Planta o interior","Talón","Rodilla"],ok:1},
    {q:"¿A qué pie se le debe pasar la pelota al compañero?",opts:["Al pie malo","Al que esté más cerca","Al pie bueno","Al que pida de talón"],ok:2},
    {q:"¿A qué poste se recomienda apuntar al disparar?",opts:["Al que esté más lejos","Al palo cercano","Al árbitro","Al cielo"],ok:1},
    {q:"¿Cómo se debe marcar al rival?",opts:["Por detrás","De frente","De costado, brazo extendido, sin derribar","Corriendo tras él"],ok:2},
    {q:"¿Qué se debe hacer antes de pedir la pelota?",opts:["Quedarse quieto","Gritar más fuerte","Desmarcarse con dos pasos y señalar","Esperar al árbitro"],ok:2},
    {q:"¿Qué error evita el equipo que quiere mantener el orden?",opts:["Salir por el centro del área","Pase largo","Tiro al arco","Corners"],ok:0}
  ];

  let idx = 0, aciertos = 0, timer = null;

  function mostrarPregunta(){
    const p = preguntas[idx];
    let html = `<div class="timer-bar"><div class="timer-fill" style="width:100%"></div></div>
                <b>Pregunta ${idx+1}/10</b> – ${p.q}<br><small id="countdown">${TIME_PER_Q}s</small><div class="mt-2">`;
    p.opts.forEach((o,k)=> html += `
      <div class="form-check">
        <input class="form-check-input" type="radio" name="opt" id="o${k}" value="${k}">
        <label class="form-check-label" for="o${k}" style="color:#fff;">${o}</label>
      </div>`);
    html += `</div><button class="btn btn-primary btn-sm mt-2" onclick="corregir()">Siguiente</button>`;
    document.getElementById('testArea').innerHTML = html;

    let seg = TIME_PER_Q;
    const bar = document.querySelector('.timer-fill');
    const txt = document.getElementById('countdown');
    timer = setInterval(()=>{
      seg--;
      bar.style.width = (seg/TIME_PER_Q*100) + '%';
      txt.textContent = seg + 's';
      if(seg === 0){ clearInterval(timer); timeOut(); }
    },1000);
  }

  function timeOut(){
    alert("Se acabó el tiempo. Volvé a intentarlo.");
    volverAlModal();
  }

  mostrarPregunta();
}

</script>
</body>
</html>
"""
# ---------- LECCIÓN 1 (texto + test) ----------
LECCION_1_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Lección 1 - Fundamentos y reglas</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body{background:#1b263b;color:#ffff00;font-family:Segoe UI,system-ui,sans-serif}
    .ventana{background:#1b263b;border-radius:12px;padding:20px;color:#ffff00}
    .btn-leer{background:#415a77;color:#ffff00;border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:15px}
    .btn-leer:hover{background:#5a7fb0}
    .timer-bar{width:100%;height:6px;background:#eee;margin-bottom:8px}
    .timer-fill{height:100%;background:#0d6efd;transition:width 1s linear}
  </style>
</head>
<body class="p-4">
<!-- dentro de LECCION_1_HTML, justo después de <body class="p-4"> -->
<style>
  .ventana{max-height:70vh; overflow-y:auto; padding:15px;}
  #testArea{max-height:60vh; overflow-y:auto;}
</style>

  <button onclick="volverAlModal()" class="btn btn-sm btn-secondary mb-3">← Volver al módulo</button>

  <div class="ventana" style="max-width:700px;margin:auto">
    <h4>Lección 1: Fundamentos y reglas del fútbol</h4>
    <div class="mt-3 p-3 bg-dark rounded small">
      <p>
        Listos para el partido esperado, el árbitro coloca el balón sobre el círculo central y pita el inicio. Cada jugador entiende que:<br>
        Primero, <strong>la mano</strong>: solo el portero puede usarla y solo dentro del rectángulo. Cualquier otro contacto es falta inmediata y, en el área, penal.<br>
        Segundo, <strong>el offside</strong>: si al recibir estás más cerca del arco que el último defensa, el banderín levanta y la jugada muere.<br>
        Tercero, <strong>el saque de banda</strong>: dos pies en el campo, balón detrás de la cabeza; si uno se adelanta o la tira mal, pierdes el saque.<br><br>

        Con las reglas claras, llegan los <strong>fundamentos</strong>:<br>
        - Controlar con el interior del pie o pisarla, no con el empeine, para que la pelota se detenga junto al pie y no tres metros adelante.<br>
        - Pasar con el interior, tobillo firme, al pie bueno del compañero: reduce un toque y evita el rebote.<br>
        - Disparar mirando al portero, no pensar al que dirán, y apuntar al poste cercano.<br>
        - En defensa, marcar de costado, brazo extendido, sin derribar.<br>
        - Desmarcarse antes de pedir: dos pasos al espacio y una señal con la mano bastan para romper líneas sin offside.<br>
        - En saques laterales, destinarla al jugador delante nuestro más cercano, llamándole la atención.<br><br>

        Las <strong>mañas</strong> permiten ganar segundos:<br>
        - Provocar que el balón golpee en las piernas del rival para ganar corners o laterales.<br>
        - Sacar rápido de banda mientras el otro discute.<br>
        - Descansar con la pelota dirigiendo el juego hacia el portero nuestro para tomar aliento y volver a empezar.<br><br>

        Pero aparecen los <strong>errores típicos del juego amateur</strong>:<br>
        - Protestar cada pitazo: amarilla gratuita, reclamarse entre nosotros muestra un equipo nervioso.<br>
        - Correr todos tras la pelota: se cierra el campo y desaparecen los pases.<br>
        - Pedirla estático: el defensa ya te tapa y perdés en la primera.<br>
        - Quedarse mirando la jugada: el rival contraataca y te coge parado en ventaja.<br>
        - Olvidan volver después de una buena jugada, no marcar hombre a hombre en saques laterales rivales y tiros de esquina.<br>
        - Salir desde el área por el centro no es recomendable, <strong>SALGA POR LOS LATERALES O A LA RAYA</strong>.<br><br>

        Cuando el árbitro pita el final, el equipo que supo conjugar reglas, fundamentos y pequeñas dosis de profesionalismo se lleva los tres puntos y la satisfacción de haber jugado al fútbol sin sobresaltos ni reclamos.
      </p>
    </div>

    <!-- Botón para desplegar el test -->
    <div class="text-center mt-4">
      <button class="btn-leer" onclick="mostrarTest()">Leído → Comenzar test</button>
    </div>

    <!-- Aquí se insertará el test más tarde -->
    <div id="testArea"></div>
    <div id="resultArea" class="mt-3"></div>
  </div>

  <script>
    function mostrarTest() {
      // Ocultamos el botón para que no lo aprieten dos veces
      document.querySelector('.btn-leer').style.display = 'none';

      const TIME_PER_Q = 6;
      const preguntas = [
        {q:"¿Quién puede usar las manos dentro del rectángulo?",opts:["Cualquier jugador","Solo el portero","El capitán","Nadie"],ok:1},
        {q:"¿Qué ocurre si estás más cerca del arco que el último defensa al recibir un pase?",opts:["Gol válido","Falta directa","Offside","Saque de meta"],ok:2},
        {q:"¿Cómo se debe realizar el saque de banda?",opts:["Con un pie en la línea","Saltando","Dos pies en el campo y pelota detrás de la cabeza","Con la mano"],ok:2},
        {q:"¿Dónde se cobra un penal?",opts:["Desde el círculo central","Desde el punto penal","Desde la banda","Desde el corner"],ok:1},
        {q:"¿Con qué parte del pie se recomienda controlar un balón alto?",opts:["Empeine","Planta o interior","Talón","Rodilla"],ok:1},
        {q:"¿A qué pie se le debe pasar la pelota al compañero?",opts:["Al pie malo","Al que esté más cerca","Al pie bueno","Al que pida de talón"],ok:2},
        {q:"¿A qué poste se recomienda apuntar al disparar?",opts:["Al que esté más lejos","Al palo cercano","Al árbitro","Al cielo"],ok:1},
        {q:"¿Cómo se debe marcar al rival?",opts:["Por detrás","De frente","De costado, brazo extendido, sin derribar","Corriendo tras él"],ok:2},
        {q:"¿Qué se debe hacer antes de pedir la pelota?",opts:["Quedarse quieto","Gritar más fuerte","Desmarcarse con dos pasos y señalar","Esperar al árbitro"],ok:2},
        {q:"¿Qué error evita el equipo que quiere mantener el orden?",opts:["Salir por el centro del área","Pase largo","Tiro al arco","Corners"],ok:0}
      ];

      let idx = 0, aciertos = 0, timer = null;

      function mostrarPregunta(){
        const p = preguntas[idx];
        let html = `<div class="timer-bar"><div class="timer-fill" style="width:100%"></div></div>
                    <b>Pregunta ${idx+1}/10</b> – ${p.q}<br><small id="countdown">${TIME_PER_Q}s</small><div class="mt-2">`;
        p.opts.forEach((o,k)=> html += `
          <div class="form-check">
            <input class="form-check-input" type="radio" name="opt" id="o${k}" value="${k}">
            <label class="form-check-label" for="o${k}" style="color:#fff;">${o}</label>
          </div>`);
        html += `</div>`;
        document.getElementById('testArea').innerHTML = html;

        let seg = TIME_PER_Q;
        const bar = document.querySelector('.timer-fill');
        const txt = document.getElementById('countdown');
        timer = setInterval(()=>{
          seg--;
          bar.style.width = (seg/TIME_PER_Q*100) + '%';
          txt.textContent = seg + 's';
          if(seg === 0){clearInterval(timer); timeOut();}
        },1000);
      }

      function timeOut(){
        alert("Se acabó el tiempo. Volvé a intentarlo.");
        volverAlModal();
      }

      function corregir(){
        const sel = document.querySelector('input[name="opt"]:checked');
        if(!sel){alert("Elegí una opción."); return;}
        clearInterval(timer);
        if(parseInt(sel.value) === preguntas[idx].ok) aciertos++;
        idx++;
        if(idx < 10){ mostrarPregunta(); } else { finalizar(); }
      }

  function finalizar(){
  const total = preguntas.length;
  if(aciertos === total){
    localStorage.setItem("modulo1","aprobado");
    document.getElementById('resultArea').innerHTML =
      `<div class="alert alert-success">Usted aprobó el módulo. ¡Felicitaciones, está listo para jugar su partido!</div>`;

    fetch("/guardar_aprobacion", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        jugador_id: 1,
        leccion_numero: 1,
        nota: aciertos
      })
    });

    // Botón para pasar a la siguiente lección
    const btnSiguiente = document.createElement('button');
    btnSiguiente.className = 'btn btn-success mt-3';
    btnSiguiente.textContent = 'Ver siguiente lección →';
    btnSiguiente.onclick = () => abrirLeccionDentro(2); // Lección 2 o la que quieras
    document.getElementById('resultArea').appendChild(btnSiguiente);

  } else {
    document.getElementById('resultArea').innerHTML =
      `<div class="alert alert-warning">Respondiste ${aciertos}/${total}. Necesitas 10/10 para aprobar.</div>`;
    setTimeout(()=> volverAlModal(), 3000);
  }
} 

      mostrarPregunta();
    }

    function volverAlModal() {
      location.reload();
    }
  </script>
</body>
</html>
"""
@app.route('/leccion/<int:n>')
def leccion(n):
    if n == 1:
        with open('templates/leccion1.html', 'r', encoding='utf-8') as f:
            html = f.read()
        return render_template_string(html)
    return "Lección no encontrada", 404


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

    html = "<h2>Lecciones Aprobadas</h2><table border='1' cellpadding='6'><tr><th>Jugador</th><th>Lección</th><th>Fecha</th><th>Nota</th></tr>"
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

    conn = psycopg2.connect(DATABASE_URL)  # esto apunta a Aiven
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO lecciones_aprobadas (jugador_id, leccion_numero, nota) VALUES (%s, %s, %s)",
        (jugador_id, leccion_numero, nota)
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}, 200

# ---------- REGISTRO RÁPIDO (crea jugador y devuelve ID) ----------
@app.route('/api/registro_rapido', methods=['POST'])
def registro_rapido():
    from datetime import date
    data = request.get_json()
    nombre = data.get('nombre')
    cedula = data.get('cedula')
    anio = data.get('anio')

    if not all([nombre, cedula, anio]):
        return {"error": "Faltan datos"}, 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jugadores (nombre, cedula, anio_nacimiento, posicion, goles, asistencias, fecha_ingreso) VALUES (%s, %s, %s, 'POR', 0, 0, %s) RETURNING id",
        (nombre, cedula, anio, date.today().isoformat())
    )
    jugador_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": jugador_id, "nombre": nombre}, 201
    
# ---------- API JSON (para el front de la lección) ----------
@app.route('/api/registro_rapido', methods=['POST'])
def api_registro_rapido():
    data = request.get_json(force=True)
    nombre = data.get('nombre')
    cedula = data.get('cedula')
    anio   = data.get('anio')

    if not all([nombre, cedula, anio]):
        return {"error": "Faltan campos"}, 400

    conn = sqlite3.connect('futbol.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO jugadores (nombre, cedula, anio_nacimiento) VALUES (?,?,?)",
                (nombre, cedula, anio))
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return {"id": nuevo_id}


@app.route('/guardar_aprobacion', methods=['POST'])
def api_guardar_aprobacion():
    data = request.get_json(force=True)
    jugador_id   = data.get('jugador_id')
    leccion_num  = data.get('leccion_numero')
    nota         = data.get('nota')

    if not all([jugador_id, leccion_num, nota]):
        return {"error": "Faltan campos"}, 400

    conn = sqlite3.connect('futbol.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO aprobaciones (jugador_id, leccion_numero, nota, fecha) VALUES (?,?,?,?)",
                (jugador_id, leccion_num, nota, date.today().isoformat()))
    conn.commit()
    conn.close()
    return {"ok": True}
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
