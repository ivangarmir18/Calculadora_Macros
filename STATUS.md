# Estado del proyecto

Última actualización: 2026-10-14

Leyenda: ✅ hecho y probado con tests · 🟡 opcional / mejora futura

## Hecho y Verificado

| Funcionalidad | Estado | Descripción y notas |
|---|---|---|
| **Backend Flask + SQLite** | ✅ | Conexión contextual segura, sin fugas de archivo en Windows, `data/` configurable. |
| **Asistente Gemini (IA y Audio de voz)** | ✅ | Grabadora de voz integrada (hasta 2 minutos) con `MediaRecorder` nativo para platos complejos y ensaladas de muchos ingredientes. Transcripción fiel en pantalla, desglose individual de ingredientes (incluyendo aliños clave como AOVE), emparejamiento con base de datos propia y cálculo de macros. Soporte adicional para fotos y texto. |
| **Ocultación y gestión de API Key** | ✅ | Soporte en `.env` (ignorado por git) o configurable en web con clave ofuscada en pantalla y protegida en SQLite. |
| **Conexión con el móvil** | ✅ | Pantalla con **código QR** y enlaces IP locales. Detección automática de IPs de red local. |
| **Interfaz y Modo Oscuro / Claro** | ✅ | Diseño responsive mobile-first (barra inferior en móvil, barra lateral en PC). Safe areas (`env(safe-area-inset)`), touch targets optimizados y prevención de zoom en Safari iOS. Tema oscuro por defecto y selector claro/oscuro/auto. |
| **Iconos vectoriales SVG** | ✅ | Sustitución completa de emojis por set vectorial SVG limpio tipo Lucide, sin dependencias externas. |
| **PWA / Instalable** | ✅ | `manifest.webmanifest`, service worker `sw.js` y set de iconos generados (180, 192, 512 y maskable). |
| **Registro de alimentos y presets** | ✅ | Buscador rápido, gramos o unidades, vista previa en tiempo real. Presets editables y multiplicador. |
| **Solo calorías (rápido)** | ✅ | Para eventos y salidas (cumpleaños, tapeo): añadir calorías globales sin desglosar. |
| **Open Food Facts + Código de barras** | ✅ | Búsqueda online de productos de supermercado con fotos oficiales y lector de código de barras. |
| **Gráficas y Progreso** | ✅ | Anillo de calorías restantes, donut de reparto por macronutrientes, gráfico de barras a 7/30/90 días. |
| **Control de peso** | ✅ | Registro diario de peso con gráfica de tendencia SVG. |
| **Calculadora de macros** | ✅ | Estimación de metabolismo basal y reparto de macros según peso, altura, edad, sexo y nivel de actividad. |
| **Copia de seguridad y exportación** | ✅ | Descarga de copia completa en JSON (con fotos) y exportación a CSV para Excel. Restauración segura contra path traversal. |
| **Seguridad con PIN opcional** | ✅ | Bloqueo con PIN de 4+ dígitos protegido con hash PBKDF2 y token seguro con cookie HttpOnly. |
| **Lanzadores portables** | ✅ | `start.bat` para Windows (doble clic) y `start.sh` para macOS/Linux con entorno virtual automático. |
| **Exportación PDF del proceso (30 días)** | ✅ | Reporte profesional en PDF con gráfica de barritas de calorías día por día, déficits acumulados vs TDEE, adherencia, pérdida de grasa estimada, macros y tabla detallada. Selector de periodo (7, 30, 90 días). |
| **CI y Tests automatizados** | ✅ | 23 tests automatizados que cubren todo el backend, validaciones, seguridad, Gemini con notas de voz y exportación. GitHub Actions configurado en Windows, Mac y Ubuntu. |

---

## Mejoras futuras sugeridas

- [ ] Soporte para modelos locales con Ollama en caso de querer usar IA sin conexión a internet.

