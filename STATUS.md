# Estado del proyecto

Última actualización: 2026-10-14

Leyenda: ✅ hecho · 🟡 hecho a medias / sin probar a fondo · ⬜ pendiente

## Hecho (MVP)

| | Funcionalidad | Notas |
|---|---|---|
| ✅ | Backend Flask + SQLite | `app.py`, `db.py`. Probado con script (CRUD, totales, histórico, validaciones). |
| ✅ | Base de datos de alimentos | Macros por 100 g, marca, unidad opcional (huevo, scoop), foto. 15 alimentos iniciales con valores **aproximados**: revísalos con tus etiquetas. |
| ✅ | Detección del día | La fecha sale del navegador (hora local). Navegación ‹ › entre días. |
| ✅ | Registro rápido de alimento | Buscador, los más usados primero, gramos o unidades, vista previa. Comida sugerida según la hora. |
| ✅ | Presets | Crear/editar/borrar. Al añadir: multiplicador global y gramos editables por ingrediente. |
| ✅ | Solo kcal manual | "Cumple ~500 kcal" sin detallar; macros opcionales. |
| ✅ | Resumen diario | kcal y macros frente a objetivos, barras, agrupado por comida. |
| ✅ | Histórico y promedio | 7/30/90 días. El promedio solo cuenta días con registros. |
| ✅ | Objetivos editables | kcal, proteína, hidratos, grasa. |
| ✅ | Foto por alimento | Subida desde el formulario del alimento. |
| 🟡 | Interfaz (HTML/CSS/JS) | Escrita pero **sin probar en navegador todavía**: puede haber fallos visuales o de JS. |

## Decisiones de diseño

- Cada entrada guarda **sus propias macros** en el momento de comerla: cambiar un alimento después no reescribe el histórico.
- Los presets son plantillas: al añadirlos se crean entradas sueltas por ingrediente (se pueden editar una a una).
- La base de datos y las fotos están en `data/` y **no se suben a git**.

## Pendiente (por orden sugerido)

1. ⬜ **Probar la UI en el navegador** y pulir lo que falle.
2. ⬜ **Entrada por texto/voz con LLM**: "me he tomado 2 huevos y una tostada" → alimentos + kcal. Plan: dictado con Web Speech API del navegador (gratis, sin audio al servidor) → endpoint `/api/parse` → LLM (Gemini/OpenAI/Claude, clave en `.env`) → propuesta editable antes de guardar. Decidir proveedor y si el audio se transcribe en el navegador o con Whisper.
3. ⬜ Copiar un día/comida a otro día ("repetir ayer").
4. ⬜ Buscar alimentos por código de barras / Open Food Facts.
5. ⬜ Gráficas (tendencia de kcal, peso).
6. ⬜ Registro de peso corporal.
7. ⬜ Instalable como PWA en el móvil (manifest + service worker).
8. ⬜ Exportar/importar copia de seguridad (CSV/JSON).
9. ⬜ Tests automáticos (ahora solo hay una prueba manual de humo).
10. ⬜ Acceso protegido si se expone fuera de la red local (ahora no hay login).

## GitHub

Repo: <https://github.com/ivangarmir18/Calculadora_Macros> (estaba vacío al empezar). Rama `main`.
