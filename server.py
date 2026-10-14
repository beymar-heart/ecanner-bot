import os
import sys
import time
import logging
import traceback

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout,
    force=True
)
log = logging.getLogger(__name__)

log.info("=" * 60)
log.info("ARRANCANDO SERVER...")
log.info("=" * 60)

# --- IMPORTS ---
try:
    log.info("Importando Flask...")
    from flask import Flask, request, jsonify
    log.info("Flask OK")
except Exception as e:
    log.error("Fallo importando Flask: %s", e)
    traceback.print_exc()
    sys.exit(1)

try:
    log.info("Importando OpenCV...")
    import cv2
    import numpy as np
    log.info("OpenCV OK")
except Exception as e:
    log.error("Fallo importando OpenCV: %s", e)
    traceback.print_exc()
    cv2 = None

try:
    log.info("Importando requests...")
    import requests
    log.info("requests OK")
except Exception as e:
    log.error("Fallo importando requests: %s", e)
    traceback.print_exc()
    sys.exit(1)

try:
    log.info("Importando google-genai...")
    from google import genai
    log.info("google-genai OK")
except Exception as e:
    log.error("Fallo importando google-genai: %s", e)
    traceback.print_exc()
    sys.exit(1)


# --- CREDENCIALES (hardcodeadas por peticion del usuario) ---
GEMINI_API_KEY     = "AQ.Ab8RN6JLXuYtkFbaYSChVIuQCvas1UoVteRG1IVoCJGtpXvWrg"
TELEGRAM_BOT_TOKEN = "8970804418:AAHpHuksoUPiqGI2acd1b7jhNHEdmbeWLl0"
TELEGRAM_CHAT_ID   = "1652211433"
GEMINI_MODEL       = "gemini-2.0-flash"

log.info("GEMINI_API_KEY presente: %s", bool(GEMINI_API_KEY))
log.info("TELEGRAM_BOT_TOKEN presente: %s", bool(TELEGRAM_BOT_TOKEN))
log.info("TELEGRAM_CHAT_ID presente: %s", bool(TELEGRAM_CHAT_ID))
log.info("Modelo Gemini: %s", GEMINI_MODEL)

# --- CLIENTE GEMINI ---
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    log.info("Cliente Gemini creado")
except Exception as e:
    log.error("Fallo creando cliente Gemini: %s", e)
    traceback.print_exc()
    client = None

# --- RUTAS ---
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH      = os.path.join(BASE_DIR, "PREVIO.jpg")
IMAGE_PROC_PATH = os.path.join(BASE_DIR, "PREVIO_proc.jpg")
PDF_PATH        = os.path.join(BASE_DIR, "TEMFISICA.pdf")

log.info("BASE_DIR: %s", BASE_DIR)
log.info("PDF existe: %s", os.path.exists(PDF_PATH))

# --- APP ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024


@app.route('/', methods=['GET'])
def home():
    return "Server funcionando. PDF: %s" % os.path.exists(PDF_PATH)


@app.route('/health', methods=['GET'])
def health():
    return jsonify(
        status="ok",
        pdf=os.path.exists(PDF_PATH),
        gemini_key=bool(GEMINI_API_KEY),
        telegram_token=bool(TELEGRAM_BOT_TOKEN),
        chat_id=bool(TELEGRAM_CHAT_ID),
        opencv=(cv2 is not None)
    )


def mejorar_imagen(path_in, path_out):
    if cv2 is None:
        log.warning("OpenCV no disponible, salto mejora")
        return path_in
    try:
        log.info("Leyendo imagen con OpenCV...")
        img = cv2.imread(path_in)
        if img is None:
            log.warning("OpenCV no pudo leer la imagen")
            return path_in
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)
        cv2.imwrite(path_out, contrast)
        log.info("Imagen mejorada y guardada")
        return path_out
    except Exception as e:
        log.error("Error OpenCV: %s", e)
        traceback.print_exc()
        return path_in


def enviar_telegram(mensaje):
    try:
        log.info("Enviando a Telegram...")
        url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_BOT_TOKEN
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": "Respuesta:\n\n" + mensaje}
        r = requests.post(url, json=payload, timeout=15)
        log.info("Telegram respondio: %s", r.status_code)
        if r.status_code != 200:
            log.warning("Telegram body: %s", r.text[:300])
    except Exception as e:
        log.error("Error Telegram: %s", e)
        traceback.print_exc()


def procesar_gemini(image_path):
    if client is None:
        log.error("Cliente Gemini no inicializado")
        return None

    max_intentos = 3
    for intento in range(max_intentos):
        image_file = None
        pdf_file = None
        try:
            log.info("Intento %d: subiendo imagen...", intento + 1)
            image_file = client.files.upload(file=image_path)
            log.info("Imagen subida: %s", image_file.name if image_file else "None")

            log.info("Intento %d: subiendo PDF...", intento + 1)
            pdf_file = client.files.upload(file=PDF_PATH)
            log.info("PDF subido: %s", pdf_file.name if pdf_file else "None")

            prompt = (
                "Analiza las preguntas de esta hoja de examen. "
                "Usa estrictamente el contenido del PDF del temario proporcionado. "
                "Solo toma en cuenta el tema 4 del pdf. "
                "Se directo y breve, maximo dos lineas, para leerse en un reloj. "
                "No parafrasees, usa el texto tal cual del pdf. "
                "REGLA: CERO EXPLICACIONES, SOLO LA RESPUESTA CON EL NUMERO DE PREGUNTA"
            )

            log.info("Llamando a Gemini (modelo %s)...", GEMINI_MODEL)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[image_file, pdf_file, prompt]
            )
            log.info("Respuesta recibida de Gemini")

            texto = response.text
            log.info("Texto: %s", texto[:200] if texto else "None")

            return texto

        except Exception as e:
            log.error("Error en intento %d: %s", intento + 1, e)
            traceback.print_exc()

            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if intento < max_intentos - 1:
                    time.sleep(2)
                    continue
            return None

        finally:
            for f in (image_file, pdf_file):
                if f:
                    try:
                        client.files.delete(name=f.name)
                    except Exception:
                        pass

    return None


@app.route('/upload', methods=['POST'])
def upload_image():
    log.info(">>> ENTRO A UPLOAD_IMAGE <<<")
    try:
        log.info("Leyendo datos de la peticion...")
        image_data = request.get_data()
        log.info("Datos recibidos: %d bytes", len(image_data))

        if not image_data:
            log.warning("No hay datos")
            return "No image data", 400

        log.info("Guardando imagen en %s", IMAGE_PATH)
        with open(IMAGE_PATH, "wb") as f:
            f.write(image_data)
        log.info("Imagen guardada")

        if not os.path.exists(PDF_PATH):
            log.error("Falta PDF")
            return "PDF missing", 500

        log.info("Mejorando imagen...")
        proc = mejorar_imagen(IMAGE_PATH, IMAGE_PROC_PATH)

        log.info("Procesando con Gemini...")
        respuesta = procesar_gemini(proc)

        if not respuesta:
            log.error("Gemini no devolvio respuesta")
            return "AI error", 500

        log.info("Enviando a Telegram...")
        enviar_telegram(respuesta)

        log.info(">>> PROCESO COMPLETO OK <<<")
        return "OK", 200

    except Exception as e:
        log.error("!!!!! ERROR EN UPLOAD !!!!!")
        log.error("Tipo: %s", type(e).__name__)
        log.error("Mensaje: %s", e)
        traceback.print_exc()
        return "Error: %s" % e, 500


if __name__ == '__main__':
    log.info("Iniciando Flask...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
