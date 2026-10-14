# Calculadora de Macros

App personal y rápida para apuntar lo que comes cada día y controlar calorías y macronutrientes.
Desarrollada con **Python (Flask)** + **HTML / CSS / JS puro** (sin frameworks pesados) + **SQLite**.

Diseñada para funcionar en cualquier PC y en el móvil, con modo oscuro/claro, iconos vectoriales SVG limpios y asistente de inteligencia artificial con **Google Gemini** para dictar comidas por voz o analizarlas con fotos.

---

## 🚀 Cómo arrancar

### En Windows (el método más fácil)
Haz **doble clic en `start.bat`**.
Se encarga de todo: crea el entorno virtual `.venv` la primera vez, instala las dependencias y abre el navegador automáticamente.

### Manualmente en terminal (Windows, Mac, Linux)
```bash
pip install -r requirements.txt
python app.py
```

Abre en tu navegador: <http://localhost:5000>

Opciones de arranque:
- `python app.py --local`: Solo accesible desde este PC.
- `python app.py --port 5001`: Cambiar el puerto.
- `python app.py --no-browser`: No abrir el navegador automáticamente.

---

## 📱 Cómo usarla en el móvil

### En casa (misma red Wi-Fi)
1. Arranca con `start.bat`.
2. Ve a **Ajustes** -> **Usar en el móvil** y escanea el código QR o entra a la IP local (ej. `http://192.168.1.50:5000`).

### Fuera de casa (con datos móviles 4G/5G o en cualquier otra red)
- **Método 1 (En 1 clic con `start_online.bat`)**:
  Haz doble clic en **`start_online.bat`**.
  Crea un túnel seguro con **HTTPS** (usando Cloudflare Tunnel gratuito, sin registrarse ni abrir puertos).
  Te dará un enlace `https://xxxx.trycloudflare.com` que puedes abrir en el móvil desde donde estés.

- **Método 2 (En la nube 24/7 sin dejar el PC encendido)**:
  En [render.com](https://render.com) o [railway.app](https://railway.app), conecta tu repositorio de GitHub recién subido y tendrás la app siempre activa con URL propia.

> **💡 Consejo PWA:** En tu navegador del móvil puedes pulsar en "Añadir a pantalla de inicio" para tenerla como una app nativa con icono propio.

---

## 🤖 Asistente Gemini (IA, Notas de Voz y Fotos)

Puedes añadir comidas grabando una nota de voz con tu propio audio, escribiendo en lenguaje natural o subiendo fotos:

- **Notas de voz (hasta 2 min)**: Pulsa en "Grabar nota de voz" y habla tranquilamente. Puedes explicar recetas con muchos ingredientes (por ejemplo: una ensalada enorme con lechuga, atún, huevo, tomate, cebolla, nueces y tu chorro de aceite de oliva). Gemini procesa el audio completo de forma multimodal, muestra en pantalla la transcripción de lo que entendió, desglosa cada ingrediente y calcula las macros exactas.
- **Fotos**: Saca una foto a tu plato o a la etiqueta nutricional de un producto.
- **Emparejamiento inteligente**: Si el alimento ya está en tu base de datos personal, Gemini lo detecta y usa tus macros exactas. Si es nuevo, calcula una estimación realista.
- **Revisión antes de guardar**: Antes de añadir a tu día, puedes revisar la transcripción, ajustar los gramos o macros de cualquier ingrediente en la vista previa o descartar los que no quieras.

### 🔑 Dónde poner tu clave de Gemini (y cómo ocultarla)

Tienes **dos formas seguras** de configurar tu API Key sin que nadie la vea y sin riesgo de subirla a GitHub:

1. **En la web (Ajustes -> Asistente Gemini)**:
   - Pega tu clave en el campo protegido.
   - Se guarda en tu base de datos local SQLite (`data/macros.db`).
   - Se muestra en pantalla ofuscada (`AIzaSy••••••••`).
   - Puedes cambiarla o borrarla cuando quieras con un solo clic.

2. **En un archivo `.env` en la raíz del proyecto**:
   - Crea un archivo llamado `.env` (puedes guiarte con `.env.example`).
   - Añade la línea:
     ```env
     GEMINI_API_KEY=tu_clave_de_gemini_aqui
     GEMINI_MODEL=gemini-3.8-flash  # Opcional (por defecto gemini-3.8-flash)
     ```
   - **Garantía de seguridad**: El archivo `.env` está en `.gitignore`, por lo que **nunca se subirá a git ni a GitHub**.

---

## ✨ Características principales

- **🍽️ Registro diario**: Detección automática del día actual (hora local del dispositivo). Navegación rápida con flechas y calendario.
- **🎯 Objetivos y macros**: Anillo interactivo de calorías restantes, barras de progreso y reparto de proteínas, carbohidratos y grasas.
- **⚡ Presets**: Crea combinaciones habituales (ej. tu batido: leche desnatada + proteína + avena). Al añadirlas puedes multiplicar todo o cambiar los gramos de cada ingrediente.
- **🔥 Solo calorías (rápido)**: Para comidas improvisadas o eventos (cumpleaños, tapeo...). Apuntas directamente "≈ 500 kcal" sin tener que desglosar ingrediente por ingrediente.
- **🥑 Alimentos y escáner**:
  - Base de datos local editable con fotos y unidades (ej. 1 huevo = 60 g, 1 scoop = 30 g).
  - Búsqueda en **Open Food Facts** integrada para importar productos del supermercado con sus fotos y macros oficiales.
  - Escáner de **código de barras** con la cámara o introduciendo el EAN.
- **📊 Progreso y Peso**:
  - Gráficas vectoriales SVG de promedio a 7, 30 y 90 días con línea de objetivo.
  - Gráfico de donut con el porcentaje real de calorías por macro.
  - Registro de peso corporal con gráfica de evolución.
  - Calculadora de necesidades calóricas integrada (fórmula Mifflin-St Jeor).
- **🔒 Seguridad (PIN opcional)**: Protege la app con un PIN de 4 dígitos si la abres en el móvil o en redes compartidas.
- **💾 Copia de seguridad**: Exporta todos tus datos (alimentos, fotos, historial, peso) en un solo archivo JSON o descarga tu histórico en CSV para Excel.

---

## 📂 Estructura del proyecto

```
CalculadoraMacros/
├── app.py                # Backend Flask y rutas API REST
├── db.py                 # Capa de base de datos SQLite y migraciones
├── gemini.py             # Cliente de IA Gemini (texto, audio y visión)
├── off.py                # Integración con Open Food Facts
├── requirements.txt      # Dependencias de Python
├── start.bat             # Lanzador 1-click para Windows
├── start.sh              # Lanzador para Linux/macOS
├── .env.example          # Plantilla para la clave de API
├── static/
│   ├── index.html        # Estructura principal
│   ├── style.css         # Temas claro/oscuro y diseño responsive
│   ├── app.js            # Lógica completa de la aplicación
│   ├── charts.js         # Gráficas SVG interactivas
│   ├── icons.js          # Iconos vectoriales limpios
│   └── icons/            # Iconos de la PWA
└── tests/
    └── test_api.py       # Suite de tests automatizados
```
