import sqlite3
from datetime import date

conn = sqlite3.connect("jugadores.db")
cursor = conn.cursor()

jugadores = [
    ("Steveen Ramon", 1996, "medio centro", 5, 5, "steveenramon.jpg"),
    ("Antony Plazante", 2004, "Mediocampista", 0, 0, "antonyplazante.jpg"),
    ("Erick Cevallos", 2002, "volante", 0,0, "erickcevallos.jpg"),
    ("Elkin Cabezas", 2007, "volante", 0, 0, "elkincabezas.jpg"),
    ("Fabian Diaz", 1995, "Delantero", 4, 3, "fabiandiaz.jpg"),
    ("jairo Rodriguez", 1986,"Delantero", 6, 5, "steveenramon.jpg"),
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

for nombre, anio, posicion, goles, asistencias, imagen in jugadores:
    cursor.execute(
        "INSERT INTO jugadores (nombre, anio_nacimiento, posicion, goles, asistencias, imagen, fecha_ingreso, pdf) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (nombre, anio, posicion, goles, asistencias, imagen, date.today().isoformat(), "")
    )

conn.commit()
conn.close()
print("✅ 5 jugadores insertados")