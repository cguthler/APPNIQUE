import psycopg2
from datetime import date

# URI de Neon (ya la tenés)
DATABASE_URL = "postgresql://neondb_owner:npg_FCk16HNmWiJg@pg-5c97c96-crisguthler2020-36f6.b.aivencloud.com:25035/defaultdb/neondb?sslmode=require"

# Datos de jugadores (nombre, año_nacimiento, posicion, goles, asistencias, imagen)
jugadores = [
    ("Steveen Ramon", 1996, "medio centro", 5, 5, "steveenramon.jpg"),
    ("Antony Plazante", 2004, "Mediocampista", 0, 0, "antonyplazante.jpg"),
    ("Erick Cevallos", 2002, "volante", 0, 0, "erickcevallos.jpg"),
    ("Elkin Cabezas", 2007, "volante", 0, 0, "elkincabezas.jpg"),
    ("Fabian Diaz", 1995, "Delantero", 4, 3, "fabiandiaz.jpg"),
    ("Jairo Rodriguez", 1986, "Delantero", 6, 5, "steveenramon.jpg"),
    ("Jorge Rosero", 2001, "extremo", 0, 5, "jorgerosero.jpg"),
    ("Ronald Aguiño", 1998, "volante", 9, 4, "ronaldaguiño.jpg"),
    ("Ronnie Gallo", 1998, "defensa", 0, 1, "ronniegallo.jpg"),
    ("Andres Aguiño", 1998, "Defensa", 0, 3, "andresaguiño.jpg"),
    ("Jhon Torres", 1986, "Delantero", 3, 5, "jhontorres.jpg"),
    ("Adrian Gavilanez", 2004, "volante", 0, 0, "adriangavilanez.jpg"),
    ("Alejandro Murillo", 2002, "volante", 0, 0, "alejandromurillo.jpg"),
    ("Antony Sellan", 1998, "defensa", 0, 0, "antonysellan.jpg"),
    ("Rony Loor", 1998, "Delantero", 6, 3, "ronyloor.jpg"),
]

# Calcular edad
def calcular_edad(anio_nacimiento):
    return date.today().year - anio_nacimiento

# Conectar a Neon
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# Insertar jugadores
for nombre, anio_nacimiento, posicion, goles, asistencias, imagen in jugadores:
    edad = calcular_edad(anio_nacimiento)
    cursor.execute(
        "INSERT INTO jugadores (nombre, edad, posicion, goles, asistencias, imagen) VALUES (%s, %s, %s, %s, %s, %s)",
        (nombre, edad, posicion, goles, asistencias, imagen)
    )

conn.commit()
cursor.close()
conn.close()
print("✅ 15 jugadores insertados en Neon")
