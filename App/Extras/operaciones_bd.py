import sqlite3
import pandas as pd
from datetime import datetime

# Ruta de la base de datos y del archivo Excel
db_path = "test_records.db"
excel_path = "Libro1.xlsm"

# Leer la hoja 'Torsiones' del archivo Excel
df = pd.read_excel(excel_path, sheet_name="Torsiones", engine="openpyxl")

# Normalizar nombres de columnas
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
print("Columnas encontradas:", df.columns.tolist())

# Conectar a la base de datos
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Eliminar todos los datos de la tabla
    cursor.execute("DELETE FROM torsion_tests")

    # Reiniciar el ID autoincrementable
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='torsion_tests'")

    # Insertar los nuevos datos desde el Excel
    for _, row in df.iterrows():
        # Convertir qty_samples a entero
        qty = int(row["qty_samples"]) if not pd.isna(row["qty_samples"]) else 0

        # Formatear test_date
        try:
            test_date = pd.to_datetime(row["test_date"]).strftime("%d/%m/%Y")
        except Exception:
            test_date = None

        cursor.execute("""
            INSERT INTO torsion_tests (test_batch, customer, test_date, qty_samples, comments, test_rig)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row["test_batch"],
            row["customer"],
            test_date,
            qty,
            row["comments"],
            row["test_rig"]
        ))

    # Confirmar los cambios
    conn.commit()
    print("✅ Datos actualizados correctamente en la tabla 'quasi_tests'.")

except Exception as e:
    print(f"❌ Error al actualizar la tabla: {e}")

finally:
    conn.close()
