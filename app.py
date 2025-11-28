# ---------------  app.py (Flask + Admin + PDF) ---------------
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory, session
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
RENDER = os.getenv("RENDER") == "true"   # variable de entorno
if RENDER:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET")
    )

app = Flask(__name__)
app.secret_key = "clave_secreta_niquee"

UPLOAD_IMG = "static/uploads"
UPLOAD_DOCS = "static/uploads/docs"
os.makedirs(UPLOAD_IMG, exist_ok=True)
os.makedirs(UPLOAD_DOCS, exist_ok=True)

ADMIN_PASSWORD = "jeremias123"
PDF_PASSWORD = "equipo"   # <-- cambia aquí tu clave

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
  <title>⚽ NIQUÉE FUTBOL CLUB</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
 <style>
  *{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:Segoe UI,system-ui,sans-serif;
  background: url("{{ url_for('static', filename='uploads/fondo.jpg') }}") no-repeat center center fixed;
  background-size: cover;
  color:#ffff00;
  font-size:16px;
  line-height:1.5;
}
  h1{
    text-align:center;
    padding:20px 0 12px;
    font-size:2rem;
    color:#000;        /* negro puro */
  }
  .wrap{
    display:flex;
    gap:20px;
    max-width:1200px;
    margin:auto;
    padding:0 20px 40px;
  }
  /* -------- columna izquierda -------- */
  .col-left{
    flex:0 0 320px;
    background:#1b263b;
    border-radius:12px;
    padding:15px;
    max-height:80vh;
    overflow-y:auto;
  }
  .logo-titulo{
  text-align:center;
  margin-bottom:15px;
  }
.logo-titulo img{
  height:80px;
  border-radius:8px;
  }
.logo-titulo h2{
  margin-top:8px;
  font-size:1.2rem;
  }
  .player{
    display:flex;
    align-items:center;
    gap:12px;
    margin-bottom:12px;
    background:#415a77;
    padding:10px;
    border-radius:8px;
  }
  .player img{
    width:60px;
    height:60px;
    object-fit:cover;
    border-radius:50%;
  }
  .info{font-size:14px}
  .info strong{
    display:block;
    font-size:15px;
    margin-bottom:2px;
  }
  /* -------- columna derecha -------- */
  .col-right{
    flex:1 1 350px;
    background:#1b263b;
    border-radius:12px;
    padding:18px;
    text-align:center;
  }
  .btns{
    margin-bottom:18px;
    display:flex;
    justify-content:center;
    gap:15px;
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
  .gallery{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
    gap:15px;
  }
  .gallery img{
    width:100%;
    height:140px;
    object-fit:cover;
    border-radius:8px;
  }
  /* -------- modal -------- */
  .modal{
    display:none;
    position:fixed;
    z-index:999;
    left:0;
    top:0;
    width:100%;
    height:100%;
    background:rgba(0,0,0,.7);
  }
  .modal-content{
    background:#1b263b;
    margin:10% auto;
    padding:25px;
    border-radius:12px;
    width:90%;
    max-width:600px;
    color:#ffff00;
    font-size:15px;
    line-height:1.5;
  }
  .close{
    color:#ffff80;
    float:right;
    font-size:22px;
    font-weight:bold;
    cursor:pointer;
  }
  .close:hover{color:#fff}
  /* -------- pie -------- */
  footer{
    text-align:center;
    padding:15px 10px;
    font-size:13px;
    background:#09101a;
    color:#ffff80;
    line-height:1.5;
  }
  @media(max-width:900px){
    .wrap{flex-direction:column}
    .col-left{flex:1 1 auto}
  }
</style>
</head>
<!--  MODAL CARGAR PDF  -->
<div id="pdfModal" class="modal">
  <div class="modal-content">
    <span class="close" onclick="document.getElementById('pdfModal').style.display='none'">&times;</span>
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
</div>

<script>
  // Enviar PDF vía JS para evitar recargar la página
  document.getElementById('pdfForm').addEventListener('submit', function (e) {
    e.preventDefault();

    const id   = document.getElementById('pdfJugador').value;
    const file = this.pdf.files[0];
    if (!file) return;

    console.log('ID →', id);
    console.log('URL →', '/subir_pdf/' + id);

    const fd = new FormData();
    fd.append('pdf', file);
    fetch('https://appniquee.onrender.com/subir_pdf/' + encodeURIComponent(id), {
   
      method: 'POST',
      body: fd
    })
      .then(() => location.reload())
      .catch(() => alert('Error al subir'));
  });
</script>
<body>
  <h1>⚽ NIQUEE FÚTBOL CLUB</h1>

  <div class="wrap">
    <!--  COLUMNA IZQUIERDA  -->
    <section class="col-left">
      <div class="logo-titulo">
        <img src="{{ url_for('static', filename='uploads/logonegronique.jpg') }}" alt="Logo">
        <h2>Plantilla de jugadores</h2>
      </div>
    {% for j in jugadores %}
<div class="player">
  <img src="{{ url_for('serve_img', name=j[6]) }}" alt="Foto">
  <div class="info">
    <strong>{{ j[1] }}</strong>
    <span>{{ j[2] }} • {{ j[3] }}</span>
    <span>G:{{ j[4] }} • A:{{ j[5] }}</span>
    {% if j[7] %}
     <a href="{{ j[7] }}" download="{{ j[1] | replace(' ', '_') }}_acta.pdf" style="color:#ffff80; font-size:13px;">📄 Descargar PDF</a>
    {% else %}
      <span style="font-size:12px;color:#aaa;">Sin PDF</span>
    {% endif %}
  </div>
</div>
{% endfor %}

    <!--  COLUMNA DERECHA  -->
    <section class="col-right">
      <div class="btns" style="display:flex; justify-content:center; gap:15px;">
        <a href="/admin" class="btn">Panel Admin</a>
        <button class="btn" onclick="document.getElementById('infoModal').style.display='block'">+ Info</button>
       <button class="btn" onclick="pedirClavePDF()">Cargar PDF</button>
      </div>
      <h2>Galería</h2>
      <div class="gallery">
        <img src="{{ url_for('static', filename='uploads/niqueeblanco.jpg') }}" alt="Equipo 1">
        <img src="{{ url_for('static', filename='uploads/logo.png') }}" alt="Equipo 2">
        <img src="{{ url_for('static', filename='uploads/gruponique.jpg') }}" alt="Equipo 3">
        <img src="{{ url_for('static', filename='uploads/niqueazul.jpg') }}" alt="Equipo 4">
      </div>
    </section>
  </div>

  <!--  MODAL  -->
  <div id="infoModal" class="modal">
    <div class="modal-content">
      <span class="close" onclick="document.getElementById('infoModal').style.display='none'">&times;</span>
      <h3>Información del Club</h3>
      <p>
        Niquee Fútbol Club nació en 2017 en Guayaquil con la filosofía de adoración a Dios, juego limpio y trabajo en equipo.
        Participamos en ligas barriales y torneos locales. ¡Buscamos talento honestidad y lealtad!<br>
        Entrenamientos: lun/mié/vie 18:00-20:00 | Cancha: sintéticas fútbol Garzota samanes<br>
        Redes: <a href="https://www.facebook.com/share/1CWH1PEHMU/  " target="_blank" style="color:#ffff80">Facebook</a>
      </p>
    </div>
  </div>

  <footer>
    @transguthler&asociados • fonos 593958787986-593992123592<br>
    cguthler@hotmail.com • <a href="https://www.facebook.com/share/1CWH1PEHMU/  " target="_blank" style="color:#ffff80">fb.me/share/1CWH1PEHMU</a><br>
    Guayaquil – Ecuador
  </footer>

<script>
  const PDF_CLAVE_CORRECTA = "{{ PDF_PASSWORD }}";  // la pasamos desde Flask

  function pedirClavePDF() {
    const intro = prompt("Introduce la contraseña para cargar PDF:");
    if (intro === PDF_CLAVE_CORRECTA) {
      document.getElementById('pdfModal').style.display = 'block';
    } else if (intro !== null) {   // null = Cancelar
      alert("❌ Contraseña incorrecta");
    }
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
    <a href="{{ j[7] }}" target="_blank">📄 Ver PDF</a> |
    <a href="/borrar/{{ j[0] }}" onclick="return confirm('¿Borrar?')">🗑️ Borrar</a>
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
    return render_template_string(INDEX_HTML, jugadores=jugadores, PDF_PASSWORD=PDF_PASSWORD)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
