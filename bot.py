import os
import subprocess
import json
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import Message
import time
import math

# Configura tu API ID y API Hash obtenidos de my.telegram.org
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')

# Crea una instancia del cliente de Pyrogram
app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Ruta del archivo JSON para ipatool_path
config_file = os.path.join(os.path.dirname(__file__), 'config.json')
ipatool_path = os.path.join(os.path.dirname(__file__), 'ipatool-2.1.4-linux-amd64')
download_folder = os.path.join(os.path.dirname(__file__), 'download')
# Base de datos SQLite
db_file = os.path.join(os.path.dirname(__file__), 'users.db')

# Funciones para interactuar con la base de datos SQLite
def init_db():
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, telegram_id INTEGER UNIQUE, user TEXT, password TEXT)''')
    conn.commit()
    conn.close()

def save_user(telegram_id, user, password):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users (telegram_id, user, password) VALUES (?, ?, ?)', (telegram_id, user, password))
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('SELECT user, password FROM users WHERE telegram_id = ?', (telegram_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row
    return None

# Función para guardar la ruta del ipatool_path en config.json
def save_ipatool_path():
    config = {
        "ipatool_path": ipatool_path
    }
    with open(config_file, 'w') as json_file:
        json.dump(config, json_file, indent=4)

# Función para cargar la ruta del ipatool_path desde config.json
def load_ipatool_path():
    if os.path.exists(config_file):
        with open(config_file, 'r') as json_file:
            config = json.load(json_file)
        return config.get("ipatool_path")
    return None

# Otras funciones
def run_command(command):
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout
    except subprocess.CalledProcessError as e:
        return None

def authenticate(ipatool_path, user, password):
    login_command = [ipatool_path, "auth", "login", "-e", user, "-p", password, "--non-interactive", "--keychain-passphrase", '0000']
    output = run_command(login_command)
    return output

def extract_value(output, key):
    key_str = f'"{key}":"'
    start_idx = output.find(key_str) + len(key_str)
    end_idx = output.find('"', start_idx)
    return output[start_idx:end_idx]

def search_app(ipatool_path, term, limit=1):
    search_command = [ipatool_path, "search", term, "--limit", str(limit), "--non-interactive", "--keychain-passphrase", '0000']
    output = run_command(search_command)
    if output:
        bundle_id = extract_value(output, "bundleID")
        name = extract_value(output, "name")
        version = extract_value(output, "version")
        return bundle_id, name, version
    return None, None, None

def download_app(ipatool_path, bundle_id, name, version, progress_callback=None):
    if bundle_id and name and version:
        output_path = os.path.join(download_folder, f"{name} v{version}.ipa")
        download_command = [ipatool_path, "download", "-b", bundle_id, "--output", output_path, "--non-interactive", "--keychain-passphrase", '0000']
        process = subprocess.Popen(download_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)

        # for line in process.stdout:
        #     decoded_line = line.decode('utf-8').strip()
        #     if "Downloading" in decoded_line:
        #         percentage = float(decoded_line.split('%')[0].split()[-1]) / 100.0
        #         if progress_callback:
        #             total_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        #             progress_callback(percentage, name, output_path, total_size)
        
        process.stdout.close()
        process.wait()
        
        if process.returncode == 0:
            if progress_callback:
                total_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                progress_callback(1.0, name, output_path, total_size)
            return output_path
        else:
            if progress_callback:
                total_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                progress_callback(0.0, name, output_path, total_size)
    return None

def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

def progress(current, total, message: Message, filename):
    bytes_uploaded = current
    total_bytes = total
    percentage = (bytes_uploaded / total_bytes) * 100

    # elapsed_time = time.time() - start_time
    # upload_speed = bytes_uploaded / elapsed_time if elapsed_time > 0 else 0
    # time_left = (total_bytes - bytes_uploaded) / upload_speed if upload_speed > 0 else 0

    message.edit_text(f"Subiendo: {filename}\n"
                      f"Progreso: {percentage:.2f}%\n"
                    #   f"Velocidad: {format_size(upload_speed)}/s\n"
                    #   f"Tiempo restante: {round(time_left)} segundos"
                      )

@app.on_message(filters.command("start"))
def start(client, message):
    message.reply_text("Hola! Estoy listo para subir archivos de la carpeta 'download'.")

@app.on_message(filters.command("config"))
def configure(client, message):
    params = message.text.split()[1:]
    if len(params) != 2:
        message.reply_text("Uso: /config <usuario> <contraseña>")
        return

    telegram_id = message.from_user.id
    user, password = params
    save_user(telegram_id, user, password)
    message.reply_text("Configuración guardada.")

@app.on_message(filters.command("download"))
def download(client, message):
    global start_time  # Definir start_time como global
    ipatool_path = load_ipatool_path()
    if not ipatool_path:
        save_ipatool_path()
        ipatool_path = load_ipatool_path()

    telegram_id = message.from_user.id
    user_data = get_user(telegram_id)
    if not user_data:
        message.reply_text("Configura primero el bot con /config <usuario> <contraseña>")
        return

    user, password = user_data
    auth_output = authenticate(ipatool_path, user, password)
    if auth_output is None:
        message.reply_text("Error en la autenticación. Verifica las credenciales.")
        return

    params = message.text.split()[1:]
    if len(params) != 1:
        message.reply_text("Uso: /download <término>")
        return

    term = params[0]
    bundle_id, name, version = search_app(ipatool_path, term)
    if not bundle_id:
        message.reply_text("No se encontró ninguna aplicación con ese término.")
        return

    progress_message = message.reply_text(f"Descargando {name} v{version}...")

    def progress_callback(percentage, filename, output_path, total_size):
        current = percentage * total_size
        progress(current, total_size, progress_message, filename)

    output_path = download_app(ipatool_path, bundle_id, name, version, progress_callback)

    if output_path:
        upload_message = message.reply_text(f"Subiendo {name} v{version}...")
        start_time = time.time()  # Iniciar el tiempo de subida
        total_size = os.path.getsize(output_path)  # Tamaño total del archivo
        client.send_document(
            message.chat.id,
            output_path,
            progress=progress,
            progress_args=(upload_message, name)
        )
        time.sleep(1)  # Añadir un pequeño retraso para asegurar que el mensaje se actualice
        upload_message.delete()

        # Eliminar el archivo después de la subida
        os.remove(output_path)
        message.reply_text(f"{name} v{version} subido")
    else:
        message.reply_text(f"Descarga de {name} v{version} falló.")

if __name__ == "__main__":
    init_db()
    print('bot run')
    app.run()
