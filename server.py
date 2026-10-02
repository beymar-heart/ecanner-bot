import os
import time
import cv2
import numpy as np
from flask import Flask, request
from google import genai
import requests  # Para enviar la notificación a tu celular

app = Flask(__name__)

# --- CONFIGURACIÓN DE CREDENCIALES ---
GEMINI_API_KEY = "AQ.Ab8RN6LA8DOI9LUvEXTYRhI7O1GxkSXThW6MmDWWA6yDzxLb4w"

# Configuración para Telegram
TELEGRAM_BOT_TOKEN = "8970804418:AAHpHuksoUPiqGI2acd1b7jhNHEdmbeWLl0"
TELEGRAM_CHAT_ID = "1652211433"

# Inicializar el cliente de Gemini con tu clave
client = genai.Client(api_key=GEMINI_API_KEY)

# Directorio y rutas de archivos locales
UPLOAD_FOLDER = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(UPLOAD_FOLDER, "PREVIO.jpg")
PDF_TEMARIO_PATH = os.path.join(UPLOAD_FOLDER, "TEMFISICA.pdf")  # Tu PDF de referencia

def mejorar_imagen_opencv(image_path):
    """Aplica CLAHE con OpenCV para mejorar el contraste de fotos movidas o de costado"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return image_path
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)
        cv2.imwrite(image_path, contrast)
    except Exception as e:
        print(f"Aviso OpenCV: {e}")
    return image_path

def enviar_notificacion_telegram(mensaje):
    """Envía la respuesta de la IA a tu Telegram para que tu celular y reloj vibren"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"🤖 Respuesta:\n\n{mensaje}"
        }
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error al enviar notificación por Telegram: {e}")

def procesar_con_ia(image_path, pdf_path):
    max_intentos = 3
    for intento in range(max_intentos):
        image_file = None
        pdf_file = None
        try:
            print(f"Subiendo archivos a la IA (Intento {intento+1})...")
            image_file = client.files.upload(file=image_path)
            pdf_file = client.files.upload(file=pdf_path)

            prompt = (
                "Analiza las preguntas de esta hoja de examen. "
                "Usa estrictamente el contenido del PDF del temario proporcionado para dar la respuesta correcta. "
                "En este caso solo toma en cuenta el tema 4 del pdf. "
                "Sé extremadamente directo, conciso y breve (máximo dos o tres líneas), optimizado para leerse rápido en un reloj. "
                "no cambies palabras ni parafrasees nada, debe ser tal cual esta escrito en el pdf, ve directo a la respuesta para que salga en 2 lineas o menos"
            )

            print("Generando respuesta con Gemini...")
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[image_file, pdf_file, prompt]
            )

            respuesta_texto = response.text
            
            # Limpiar archivos de los servidores de Google
            if image_file: client.files.delete(name=image_file.name)
            if pdf_file: client.files.delete(name=pdf_file.name)

            return respuesta_texto

        except Exception as e:
            print(f"Error en intento {intento+1}: {e}")
            # Intentar limpiar archivos si quedaron colgados
            try:
                if image_file: client.files.delete(name=image_file.name)
                if pdf_file: client.files.delete(name=pdf_file.name)
            except:
                pass

            # Si es un error 503 (servidores saturados), reintentar automáticamente
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if intento < max_intentos - 1:
                    print("Servidores saturados (503). Reintentando en 1.5 segundos...")
                    time.sleep(1.5)
                    continue
            break  # Si es otro tipo de error, rompemos el ciclo

    return None

@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        image_data = request.get_data()
        if not image_data:
            return "No image data received", 400

        # Guardar la foto que mandó el ESP32
        with open(IMAGE_PATH, "wb") as f:
            f.write(image_data)

        print(f"¡Foto recibida del ESP32! Tamaño: {len(image_data)} bytes")

        # Mejorar con OpenCV
        mejorar_imagen_opencv(IMAGE_PATH)

        if not os.path.exists(PDF_TEMARIO_PATH):
            print("Error: Falta el archivo 'temario.pdf' en la carpeta.")
            return "Temario missing", 500

        # Procesar con la API de Google (con reintentos automáticos si hay 503)
        respuesta_final = procesar_con_ia(IMAGE_PATH, PDF_TEMARIO_PATH)

        if respuesta_final:
            print(f"\nRespuesta obtenida: {respuesta_final}")
            enviar_notificacion_telegram(respuesta_final)
            return "OK", 200
        else:
            return "Error procesando IA", 500

    except Exception as e:
        print(f"Error en el servidor: {e}")
        return "Internal Server Error", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)