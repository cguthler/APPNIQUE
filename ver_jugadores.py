import sqlite3

conn = sqlite3.connect("jugadores.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM jugadores")
filas = cursor.fetchall()

if not filas:
    print("❌ No hay jugadores guardados.")
else:
    print("✅ Jugadores encontrados:")
    for f in filas:
        print(f)

conn.close()