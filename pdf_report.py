"""Generador de informes PDF para la Calculadora de Macros usando fpdf2.

Soporta informe de día individual o reporte completo del proceso de los últimos X días
(7, 14, 30, 90 días) con gráfica de barras de calorías, métricas de déficit y tabla detallada.
"""
import io
from datetime import date, datetime, timedelta
from fpdf import FPDF, XPos, YPos


class MacroPDF(FPDF):
    def __init__(self, title_text="Informe Nutricional - Calculadora de Macros"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_title(title_text)
        self.set_author("Calculadora de Macros")

    def header(self):
        # Franja superior verde esmeralda
        self.set_fill_color(16, 185, 129)
        self.rect(0, 0, 210, 5, "F")

    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Calculadora de Macros - Página {self.page_no()}/{{nb}}", align="C")


def generate_macro_pdf(conn, target_date=None, days_range=30):
    """Genera un archivo PDF binario con el informe nutricional, métricas biométricas,
    gráfica de barras de calorías y tabla detallada de evolución del proceso."""
    target_date = target_date or date.today().isoformat()
    target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Leer settings y objetivos
    settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in settings_rows}

    goal_kcal = float(settings.get("goal_kcal", "2150"))
    goal_p = float(settings.get("goal_protein", "185"))
    goal_c = float(settings.get("goal_carbs", "200"))
    goal_f = float(settings.get("goal_fat", "65"))

    tdee = float(settings.get("profile_tdee", "3350"))
    weight = float(settings.get("profile_weight", "119"))
    lbm = float(settings.get("profile_lbm", "85.5"))
    fat_mass = max(0.0, weight - lbm)
    fat_pct = (fat_mass / weight * 100.0) if weight > 0 else 0.0
    planned_deficit = tdee - goal_kcal
    prot_per_lbm = (goal_p / lbm) if lbm > 0 else 0.0

    # Construir lista cronológica completa para el rango de días [target_date - days + 1, target_date]
    start_dt = target_date_obj - timedelta(days=days_range - 1)
    date_strs = [(start_dt + timedelta(days=i)).isoformat() for i in range(days_range)]

    # Consultar entradas agregadas por día
    entries_sql = """
        SELECT date,
               ROUND(SUM(kcal), 1) as kcal,
               ROUND(SUM(protein), 1) as protein,
               ROUND(SUM(carbs), 1) as carbs,
               ROUND(SUM(fat), 1) as fat,
               COUNT(*) as n_items
        FROM entries
        WHERE date >= ? AND date <= ?
        GROUP BY date
    """
    entries_by_date = {
        r["date"]: dict(r)
        for r in conn.execute(entries_sql, (date_strs[0], date_strs[-1])).fetchall()
    }

    # Consultar pesos registrados en el rango
    weights_sql = "SELECT date, kg FROM weights WHERE date >= ? AND date <= ? ORDER BY date"
    weights_by_date = {
        r["date"]: r["kg"]
        for r in conn.execute(weights_sql, (date_strs[0], date_strs[-1])).fetchall()
    }

    # Combinar información por día
    period_days = []
    for dt in date_strs:
        ent = entries_by_date.get(dt, {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "n_items": 0})
        w_kg = weights_by_date.get(dt)
        period_days.append({
            "date": dt,
            "kcal": ent["kcal"],
            "protein": ent["protein"],
            "carbs": ent["carbs"],
            "fat": ent["fat"],
            "has_data": ent["kcal"] > 0 or ent["n_items"] > 0,
            "weight": w_kg,
        })

    # Estadísticas del periodo
    logged_days_list = [d for d in period_days if d["has_data"]]
    n_logged = len(logged_days_list)
    adherence_pct = (n_logged / days_range * 100.0) if days_range > 0 else 0.0

    avg_kcal = (sum(d["kcal"] for d in logged_days_list) / n_logged) if n_logged > 0 else 0.0
    avg_p = (sum(d["protein"] for d in logged_days_list) / n_logged) if n_logged > 0 else 0.0
    avg_c = (sum(d["carbs"] for d in logged_days_list) / n_logged) if n_logged > 0 else 0.0
    avg_f = (sum(d["fat"] for d in logged_days_list) / n_logged) if n_logged > 0 else 0.0

    total_kcal_period = sum(d["kcal"] for d in logged_days_list)
    # Déficit total acumulado en los días registrados
    total_deficit = sum((tdee - d["kcal"]) for d in logged_days_list)
    fat_loss_est_kg = total_deficit / 7700.0 if total_deficit > 0 else 0.0

    # Crear documento PDF
    title_text = f"Informe de Proceso - Últimos {days_range} Días"
    pdf = MacroPDF(title_text)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_y(10)

    # ----------------------------------------------------
    # TÍTULO DEL INFORME
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42)
    period_label = f"ÚLTIMOS {days_range} DÍAS" if days_range > 1 else "REGISTRO DIARIO"
    pdf.cell(0, 8, f"INFORME DE PROCESO & MACROS - {period_label}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(100, 116, 139)
    date_info = f"Periodo: {date_strs[0]} al {date_strs[-1]}   |   Generado el {now_str}"
    pdf.cell(0, 5, date_info, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # ----------------------------------------------------
    # SECCIÓN 1: Perfil y Parámetros Biométricos
    # ----------------------------------------------------
    y_bio = pdf.get_y()
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, y_bio, 190, 26, "DF")

    pdf.set_xy(14, y_bio + 2)
    pdf.set_font("helvetica", "B", 9.5)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(0, 4.5, "OBJETIVOS Y PARÁMETROS BIOMÉTRICOS DEL USUARIO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.set_x(14)
    line1 = (
        f"- Gasto Calórico (TDEE): {tdee:.0f} kcal   |   "
        f"Objetivo Diario: {goal_kcal:.0f} kcal   |   "
        f"Déficit Planificado: -{planned_deficit:.0f} kcal/día"
    )
    pdf.cell(0, 4.5, line1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(14)
    line2 = (
        f"- Peso Actual: {weight:.1f} kg   |   "
        f"Masa Magra (LBM): {lbm:.1f} kg   |   "
        f"Grasa Estimada: {fat_mass:.1f} kg ({fat_pct:.1f}%)"
    )
    pdf.cell(0, 4.5, line2, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(14)
    line3 = (
        f"- Reparto Objetivo: {goal_p:.0f}g Proteína ({prot_per_lbm:.2f} g/kg LBM)   |   "
        f"{goal_c:.0f}g Carbohidratos   |   {goal_f:.0f}g Grasas"
    )
    pdf.cell(0, 4.5, line3, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(y_bio + 30)

    # ----------------------------------------------------
    # SECCIÓN 2: 4 Tarjetas de Resumen Global del Periodo
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 5, f"Resumen Global del Proceso ({days_range} Días)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    card_w = 45
    card_h = 22
    y_cards = pdf.get_y()

    cards = [
        (
            "Adherencia al Registro",
            f"{n_logged} / {days_range} días",
            f"{adherence_pct:.0f}% completado",
            (16, 185, 129) if adherence_pct >= 70 else (217, 119, 6)
        ),
        (
            "Promedio Calórico",
            f"{avg_kcal:.0f} kcal" if n_logged else "-",
            f"Obj: {goal_kcal:.0f} kcal",
            (16, 185, 129) if avg_kcal <= goal_kcal else (239, 68, 68)
        ),
        (
            "Déficit Acumulado",
            f"-{total_deficit:,.0f} kcal".replace(",", ".") if n_logged else "-",
            f"vs TDEE ({tdee:.0f} kcal)",
            (37, 99, 235)
        ),
        (
            "Grasa Quemada Est.",
            f"~ -{fat_loss_est_kg:.1f} kg" if total_deficit > 0 else "0.0 kg",
            "Base: 7.700 kcal/kg",
            (249, 115, 22)
        ),
    ]

    for idx, (title, val, sub, col) in enumerate(cards):
        x = 10 + idx * 48
        pdf.set_xy(x, y_cards)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(x, y_cards, card_w, card_h, "DF")

        pdf.set_xy(x + 2, y_cards + 2)
        pdf.set_font("helvetica", "B", 7.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(card_w - 4, 3.5, title, align="C")

        pdf.set_xy(x + 2, y_cards + 6.5)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(*col)
        pdf.cell(card_w - 4, 6.5, val, align="C")

        pdf.set_xy(x + 2, y_cards + 14)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(card_w - 4, 3.5, sub, align="C")

    pdf.set_y(y_cards + card_h + 5)

    # ----------------------------------------------------
    # SECCIÓN 3: Gráfica de Barras de Calorías Diarias
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 5, "Evolución de Calorías Diarias (Gráfica de Barritas)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    chart_x = 10
    chart_y = pdf.get_y()
    chart_w = 190
    chart_h = 44

    # Fondo del área del gráfico
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(chart_x, chart_y, chart_w, chart_h, "DF")

    # Escala vertical: máximo entre el pico de kcal y 2600 kcal
    max_logged_kcal = max([d["kcal"] for d in period_days] or [0])
    max_y = max(2600.0, max_logged_kcal * 1.15, goal_kcal * 1.25)
    inner_x = chart_x + 16
    inner_y = chart_y + 4
    inner_w = chart_w - 20
    inner_h = chart_h - 12
    bottom_y = inner_y + inner_h

    # Líneas de referencia y etiquetas en eje Y (ej: 0, 1000, 2000, max_y)
    pdf.set_font("helvetica", "", 6.5)
    pdf.set_text_color(140, 140, 140)
    y_steps = [0, 1000, 2000, int(round(max_y / 500) * 500)]
    for y_val in y_steps:
        if y_val > max_y:
            continue
        y_pos = bottom_y - (y_val / max_y) * inner_h
        pdf.set_draw_color(241, 245, 249)
        pdf.line(inner_x, y_pos, inner_x + inner_w, y_pos)
        pdf.set_xy(chart_x + 1, y_pos - 2)
        pdf.cell(14, 4, f"{y_val}", align="R")

    # Línea discontinua de Objetivo Calórico Diario (Naranja)
    goal_y_pos = bottom_y - (goal_kcal / max_y) * inner_h
    pdf.set_draw_color(249, 115, 22)
    pdf.set_dash_pattern(dash=2, gap=1.5)
    pdf.line(inner_x, goal_y_pos, inner_x + inner_w, goal_y_pos)
    pdf.set_dash_pattern()  # restaurar trazo normal
    pdf.set_xy(inner_x + inner_w - 40, goal_y_pos - 4)
    pdf.set_font("helvetica", "B", 6.5)
    pdf.set_text_color(249, 115, 22)
    pdf.cell(40, 3.5, f"Objetivo: {goal_kcal:.0f} kcal", align="R")

    # Dibujar cada una de las barritas de los días
    n_bars = len(period_days)
    slot_w = inner_w / n_bars
    bar_w = max(1.8, slot_w * 0.72)

    for i, d in enumerate(period_days):
        bx = inner_x + (i * slot_w) + (slot_w - bar_w) / 2
        k = d["kcal"]

        if k > 0:
            bh = max(1.5, (k / max_y) * inner_h)
            by = bottom_y - bh
            # Color de barra: Verde si en objetivo o en margen de tolerancia (+10%), Rojo si superó con exceso
            if k <= goal_kcal * 1.10:
                pdf.set_fill_color(16, 185, 129)  # Verde esmeralda (en rango / tolerancia)
                pdf.set_draw_color(13, 148, 136)
            else:
                pdf.set_fill_color(239, 68, 68)   # Rojo / exceso real (>10%)
                pdf.set_draw_color(220, 38, 38)
            pdf.rect(bx, by, bar_w, bh, "DF")
        else:
            # Barra tenue para indicar día sin registrar
            pdf.set_fill_color(226, 232, 240)
            pdf.set_draw_color(203, 213, 225)
            pdf.rect(bx, bottom_y - 1.2, bar_w, 1.2, "DF")

        # Etiquetas en eje X: cada pocos días según el número total de días
        step_label = 1 if n_bars <= 10 else (3 if n_bars <= 20 else (5 if n_bars <= 40 else 10))
        if i % step_label == 0 or i == n_bars - 1:
            day_str = d["date"].split("-")[2] + "/" + d["date"].split("-")[1]
            pdf.set_xy(bx - 3, bottom_y + 1)
            pdf.set_font("helvetica", "", 6)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(bar_w + 6, 3, day_str, align="C")

    # Leyenda al pie de la gráfica
    pdf.set_y(chart_y + chart_h + 2)
    pdf.set_font("helvetica", "", 7.5)

    leg_x = 14
    leg_y = pdf.get_y()

    # Verde: en objetivo (tolerancia 10%)
    pdf.set_fill_color(16, 185, 129)
    pdf.rect(leg_x, leg_y + 1, 3.5, 3.5, "F")
    pdf.set_xy(leg_x + 5, leg_y)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(48, 5, "En objetivo (tolerancia 10%)")

    # Rojo: exceso
    leg_x2 = leg_x + 52
    pdf.set_fill_color(239, 68, 68)
    pdf.rect(leg_x2, leg_y + 1, 3.5, 3.5, "F")
    pdf.set_xy(leg_x2 + 5, leg_y)
    pdf.cell(32, 5, "Exceso (>10%)")

    # Gris: sin registro
    leg_x3 = leg_x2 + 38
    pdf.set_fill_color(226, 232, 240)
    pdf.rect(leg_x3, leg_y + 1, 3.5, 3.5, "F")
    pdf.set_xy(leg_x3 + 5, leg_y)
    pdf.cell(28, 5, "Sin registro")

    # Naranja: Línea objetivo
    leg_x4 = leg_x3 + 34
    pdf.set_draw_color(249, 115, 22)
    pdf.set_dash_pattern(dash=1.5, gap=1)
    pdf.line(leg_x4, leg_y + 2.5, leg_x4 + 6, leg_y + 2.5)
    pdf.set_dash_pattern()
    pdf.set_xy(leg_x4 + 8, leg_y)
    pdf.cell(45, 5, f"Meta: {goal_kcal:.0f} kcal/día")

    pdf.ln(7)

    # ----------------------------------------------------
    # SECCIÓN 4: Tabla Detallada Día por Día
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 5, f"Detalle Día por Día ({days_range} Días analizados)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    # Ancho de columnas: total = 190 mm
    # Fecha: 28 mm, Kcal: 18 mm, Mini Barra: 24 mm, Déficit: 24 mm, P: 18 mm, C: 18 mm, F: 18 mm, Peso: 22 mm, Comidas: 20 mm
    col_w = [26, 18, 24, 24, 18, 18, 18, 22, 22]
    headers = ["Fecha", "Kcal", "Progreso", "Déficit vs TDEE", "Prot (g)", "Hidr (g)", "Grasa (g)", "Peso (kg)", "Registros"]

    def print_table_header():
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 7.5)
        for w, h in zip(col_w, headers):
            pdf.cell(w, 5.5, h, border=1, fill=True, align="C")
        pdf.ln()

    print_table_header()

    fill = False
    weekday_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    # Mostramos los días en orden cronológico inverso (del más reciente al más antiguo)
    for d in reversed(period_days):
        # Salto de página automático si queda poco espacio
        if pdf.get_y() > 270:
            pdf.add_page()
            print_table_header()

        d_obj = datetime.strptime(d["date"], "%Y-%m-%d").date()
        w_name = weekday_es[d_obj.weekday()]
        date_formatted = f"{w_name} {d_obj.strftime('%d/%m')}"

        pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(30, 41, 59)

        row_y = pdf.get_y()
        row_h = 5.2

        if d["has_data"]:
            kcal_str = f"{d['kcal']:.0f}"
            def_val = tdee - d["kcal"]
            def_str = f"-{def_val:.0f} kcal" if def_val > 0 else f"+{abs(def_val):.0f} kcal"
            p_str = f"{d['protein']:.1f}"
            c_str = f"{d['carbs']:.1f}"
            f_str = f"{d['fat']:.1f}"
            w_str = f"{d['weight']:.1f} kg" if d["weight"] else "-"
            status_txt = "Registrado"
        else:
            kcal_str = "-"
            def_str = "-"
            p_str = "-"
            c_str = "-"
            f_str = "-"
            w_str = f"{d['weight']:.1f} kg" if d["weight"] else "-"
            status_txt = "Sin datos"

        # Celda 0: Fecha
        pdf.cell(col_w[0], row_h, date_formatted, border=1, fill=fill, align="L")
        # Celda 1: Kcal
        pdf.cell(col_w[1], row_h, kcal_str, border=1, fill=fill, align="R")

        # Celda 2: Mini barra visual
        # Dibujar celda vacía con borde
        cur_x = pdf.get_x()
        cur_y = pdf.get_y()
        pdf.cell(col_w[2], row_h, "", border=1, fill=fill)

        # Dibujar barra dentro
        if d["has_data"] and d["kcal"] > 0:
            bar_track_w = col_w[2] - 4
            bar_fill_w = min(bar_track_w, (d["kcal"] / goal_kcal) * bar_track_w)
            pdf.set_fill_color(226, 232, 240)
            pdf.rect(cur_x + 2, cur_y + 1.2, bar_track_w, 2.8, "F")
            # Color de progreso (tolerancia del 10%)
            if d["kcal"] <= goal_kcal * 1.10:
                pdf.set_fill_color(16, 185, 129)
            else:
                pdf.set_fill_color(239, 68, 68)
            pdf.rect(cur_x + 2, cur_y + 1.2, bar_fill_w, 2.8, "F")

        # Celda 3: Déficit
        pdf.set_xy(cur_x + col_w[2], cur_y)
        if d["has_data"] and (tdee - d["kcal"]) > 0:
            pdf.set_text_color(16, 185, 129)
        elif d["has_data"]:
            pdf.set_text_color(239, 68, 68)
        else:
            pdf.set_text_color(140, 140, 140)
        pdf.cell(col_w[3], row_h, def_str, border=1, fill=fill, align="R")

        # Celdas 4, 5, 6: Macros
        pdf.set_text_color(30, 41, 59)
        pdf.cell(col_w[4], row_h, p_str, border=1, fill=fill, align="R")
        pdf.cell(col_w[5], row_h, c_str, border=1, fill=fill, align="R")
        pdf.cell(col_w[6], row_h, f_str, border=1, fill=fill, align="R")

        # Celda 7: Peso
        if d["weight"]:
            pdf.set_font("helvetica", "B", 7.5)
            pdf.set_text_color(37, 99, 235)
        else:
            pdf.set_font("helvetica", "", 7.5)
            pdf.set_text_color(140, 140, 140)
        pdf.cell(col_w[7], row_h, w_str, border=1, fill=fill, align="C")

        # Celda 8: Estado
        pdf.set_font("helvetica", "", 7)
        pdf.set_text_color(100, 116, 139) if d["has_data"] else pdf.set_text_color(160, 160, 160)
        pdf.cell(col_w[8], row_h, status_txt, border=1, fill=fill, align="C")

        pdf.ln()
        fill = not fill

    # Fila de PROMEDIOS / TOTALES
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(col_w[0], 6, "PROMEDIO", border=1, fill=True, align="L")
    pdf.cell(col_w[1], 6, f"{avg_kcal:.0f}", border=1, fill=True, align="R")
    pdf.cell(col_w[2], 6, "", border=1, fill=True)
    avg_def = tdee - avg_kcal
    pdf.cell(col_w[3], 6, f"-{avg_def:.0f} kcal" if avg_def > 0 else f"+{abs(avg_def):.0f}", border=1, fill=True, align="R")
    pdf.cell(col_w[4], 6, f"{avg_p:.1f}", border=1, fill=True, align="R")
    pdf.cell(col_w[5], 6, f"{avg_c:.1f}", border=1, fill=True, align="R")
    pdf.cell(col_w[6], 6, f"{avg_f:.1f}", border=1, fill=True, align="R")
    pdf.cell(col_w[7] + col_w[8], 6, f"Adherencia: {adherence_pct:.0f}%", border=1, fill=True, align="C")
    pdf.ln(8)

    # Generar bytes de salida
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def compute_weekly_summary(conn, target_date=None, weeks_count=12):
    """Agrupa entradas y pesos por semana (lunes a domingo) durante las últimas `weeks_count` semanas
    (ej. 12 semanas o 52 semanas) y devuelve estadísticas por semana y globales."""
    target_date = target_date or date.today().isoformat()
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    current_monday = target_dt - timedelta(days=target_dt.weekday())
    first_monday = current_monday - timedelta(days=(weeks_count - 1) * 7)
    last_sunday = current_monday + timedelta(days=6)

    settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in settings_rows}
    goal_kcal = float(settings.get("goal_kcal", "2150"))
    goal_p = float(settings.get("goal_protein", "185"))
    goal_c = float(settings.get("goal_carbs", "200"))
    goal_f = float(settings.get("goal_fat", "65"))
    tdee = float(settings.get("profile_tdee", "3350"))
    weight = float(settings.get("profile_weight", "119"))
    lbm = float(settings.get("profile_lbm", "85.5"))

    # Entradas diarias en todo el rango
    entries_sql = """
        SELECT date,
               ROUND(SUM(kcal), 1) as kcal,
               ROUND(SUM(protein), 1) as protein,
               ROUND(SUM(carbs), 1) as carbs,
               ROUND(SUM(fat), 1) as fat,
               COUNT(*) as n_items
        FROM entries
        WHERE date >= ? AND date <= ?
        GROUP BY date
    """
    entries_by_date = {
        r["date"]: dict(r)
        for r in conn.execute(entries_sql, (first_monday.isoformat(), last_sunday.isoformat())).fetchall()
    }

    weights_sql = "SELECT date, kg FROM weights WHERE date >= ? AND date <= ? ORDER BY date"
    weights_by_date = {
        r["date"]: float(r["kg"])
        for r in conn.execute(weights_sql, (first_monday.isoformat(), last_sunday.isoformat())).fetchall()
    }

    weeks = []
    prev_avg_weight = None
    all_logged_days = []
    all_weights_in_period = []

    for idx in range(weeks_count):
        w_start = first_monday + timedelta(days=idx * 7)
        w_end = w_start + timedelta(days=6)
        iso_y, iso_w, _ = w_start.isocalendar()

        day_list = []
        w_weights = []
        for d_off in range(7):
            d_str = (w_start + timedelta(days=d_off)).isoformat()
            if d_str in entries_by_date:
                ent = entries_by_date[d_str]
                if ent["kcal"] > 0 or ent["n_items"] > 0:
                    day_list.append(ent)
                    all_logged_days.append(ent)
            if d_str in weights_by_date:
                w_weights.append(weights_by_date[d_str])
                all_weights_in_period.append((d_str, weights_by_date[d_str]))

        n_days = len(day_list)
        if n_days > 0:
            avg_k = round(sum(x["kcal"] for x in day_list) / n_days, 1)
            avg_pr = round(sum(x["protein"] for x in day_list) / n_days, 1)
            avg_cb = round(sum(x["carbs"] for x in day_list) / n_days, 1)
            avg_ft = round(sum(x["fat"] for x in day_list) / n_days, 1)
            tot_def = round(sum(tdee - x["kcal"] for x in day_list), 0)
            avg_def = round(tdee - avg_k, 0)
        else:
            avg_k = avg_pr = avg_cb = avg_ft = tot_def = avg_def = 0.0

        avg_w = round(sum(w_weights) / len(w_weights), 1) if w_weights else None
        w_diff = round(avg_w - prev_avg_weight, 1) if (avg_w is not None and prev_avg_weight is not None) else None
        if avg_w is not None:
            prev_avg_weight = avg_w

        weeks.append({
            "index": idx + 1,
            "iso_year": iso_y,
            "iso_week": iso_w,
            "start_date": w_start.isoformat(),
            "end_date": w_end.isoformat(),
            "label": f"Sem {iso_w} ({w_start.strftime('%d/%m')} - {w_end.strftime('%d/%m')})",
            "short_label": f"S{iso_w}",
            "logged_days": n_days,
            "kcal": avg_k,
            "protein": avg_pr,
            "carbs": avg_cb,
            "fat": avg_ft,
            "avg_deficit": avg_def,
            "total_deficit": tot_def,
            "avg_weight": avg_w,
            "weight_diff": w_diff,
            "weights_count": len(w_weights),
        })

    total_logged = len(all_logged_days)
    active_weeks = sum(1 for w in weeks if w["logged_days"] > 0)
    g_avg_kcal = round(sum(x["kcal"] for x in all_logged_days) / total_logged, 1) if total_logged else 0.0
    g_avg_p = round(sum(x["protein"] for x in all_logged_days) / total_logged, 1) if total_logged else 0.0
    g_avg_c = round(sum(x["carbs"] for x in all_logged_days) / total_logged, 1) if total_logged else 0.0
    g_avg_f = round(sum(x["fat"] for x in all_logged_days) / total_logged, 1) if total_logged else 0.0
    g_tot_def = round(sum(tdee - x["kcal"] for x in all_logged_days), 0)
    g_fat_loss_kg = round(g_tot_def / 7700.0, 2) if g_tot_def > 0 else 0.0

    start_w = all_weights_in_period[0][1] if all_weights_in_period else None
    end_w = all_weights_in_period[-1][1] if all_weights_in_period else None
    w_change = round(end_w - start_w, 1) if (start_w is not None and end_w is not None) else None

    return {
        "weeks_count": weeks_count,
        "start_date": first_monday.isoformat(),
        "end_date": last_sunday.isoformat(),
        "weeks": weeks,
        "active_weeks": active_weeks,
        "total_logged_days": total_logged,
        "average": {
            "kcal": g_avg_kcal,
            "protein": g_avg_p,
            "carbs": g_avg_c,
            "fat": g_avg_f,
        },
        "total_deficit": g_tot_def,
        "est_fat_loss_kg": g_fat_loss_kg,
        "start_weight": start_w,
        "end_weight": end_w,
        "weight_change": w_change,
        "goals": {"kcal": goal_kcal, "protein": goal_p, "carbs": goal_c, "fat": goal_f},
        "biometrics": {"tdee": tdee, "weight": end_w or weight, "lbm": lbm},
    }


def generate_weekly_pdf(conn, target_date=None, weeks_count=12):
    """Genera un informe PDF ejecutivo por semanas (12 o 52 semanas) con gráfica de evolución
    semanal y tabla desglosada semana a semana (calorías, macros, déficit y peso medio)."""
    summary = compute_weekly_summary(conn, target_date=target_date, weeks_count=weeks_count)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    g = summary["goals"]
    bio = summary["biometrics"]
    avg = summary["average"]
    weeks = summary["weeks"]
    tdee = bio["tdee"]
    goal_kcal = g["kcal"]

    title_text = f"Informe por Semanas - Últimas {weeks_count} Semanas"
    pdf = MacroPDF(title_text)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_y(10)

    # Título
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, f"INFORME DE EVOLUCIÓN SEMANAL ({weeks_count} SEMANAS)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(
        0, 5,
        f"Periodo: {summary['start_date']} al {summary['end_date']}   |   Generado el {now_str}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(3)

    # Resumen global del bloque de semanas
    y_box = pdf.get_y()
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, y_box, 190, 28, "DF")

    pdf.set_xy(14, y_box + 2)
    pdf.set_font("helvetica", "B", 9.5)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(0, 5, f"BALANCE GLOBAL DE LAS ÚLTIMAS {weeks_count} SEMANAS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.set_x(14)
    pdf.cell(
        0, 4.5,
        f"- Semanas activas: {summary['active_weeks']}/{weeks_count} ({summary['total_logged_days']} días registrados)   |   "
        f"Media Diaria: {avg['kcal']:.0f} kcal (Obj: {goal_kcal:.0f} / TDEE: {tdee:.0f})",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_x(14)
    pdf.cell(
        0, 4.5,
        f"- Macros Medios: Proteína {avg['protein']:.1f}g (Obj {g['protein']:.0f}g) · "
        f"Hidratos {avg['carbs']:.1f}g (Obj {g['carbs']:.0f}g) · Grasa {avg['fat']:.1f}g (Obj {g['fat']:.0f}g)",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_x(14)
    w_txt = (
        f"Peso inicial: {summary['start_weight']:.1f} kg -> Actual: {summary['end_weight']:.1f} kg "
        f"({summary['weight_change']:+.1f} kg)"
        if summary["start_weight"] is not None and summary["end_weight"] is not None
        else f"Peso de perfil: {bio['weight']:.1f} kg"
    )
    pdf.cell(
        0, 4.5,
        f"- Déficit Acumulado: -{summary['total_deficit']:.0f} kcal (~{summary['est_fat_loss_kg']:.2f} kg grasa teórica)   |   {w_txt}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_y(y_box + 32)

    # Gráfica de barras por semana
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, f"1. GRÁFICA DE INGESTA MEDIA SEMANAL ({weeks_count} SEMANAS)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    chart_x, chart_y, chart_w, chart_h = 10, pdf.get_y() + 1, 190, 42
    pdf.set_fill_color(252, 253, 255)
    pdf.set_draw_color(203, 213, 225)
    pdf.rect(chart_x, chart_y, chart_w, chart_h, "DF")

    max_val = max([tdee, goal_kcal * 1.15] + [w["kcal"] for w in weeks]) * 1.08
    if max_val <= 0:
        max_val = 3500.0

    plot_x = chart_x + 12
    plot_y = chart_y + 4
    plot_w = chart_w - 16
    plot_h = chart_h - 11

    # Líneas guía: Objetivo y TDEE
    goal_y = plot_y + plot_h - (goal_kcal / max_val * plot_h)
    tdee_y = plot_y + plot_h - (tdee / max_val * plot_h)
    pdf.set_draw_color(245, 158, 11)
    pdf.line(plot_x, goal_y, plot_x + plot_w, goal_y)
    pdf.set_draw_color(59, 130, 246)
    pdf.line(plot_x, tdee_y, plot_x + plot_w, tdee_y)

    pdf.set_font("helvetica", "", 6)
    pdf.set_text_color(100, 116, 139)
    pdf.set_xy(chart_x + 1, goal_y - 2)
    pdf.cell(10, 4, f"{goal_kcal:.0f}", align="R")
    pdf.set_xy(chart_x + 1, tdee_y - 2)
    pdf.cell(10, 4, f"{tdee:.0f}", align="R")

    n_bars = len(weeks)
    slot_w = plot_w / max(1, n_bars)
    bar_w = max(1.2, min(8.0, slot_w * 0.68))

    for i, w in enumerate(weeks):
        bx = plot_x + i * slot_w + (slot_w - bar_w) / 2.0
        if w["kcal"] > 0:
            bh = min(plot_h, (w["kcal"] / max_val) * plot_h)
            by = plot_y + plot_h - bh
            if w["kcal"] <= goal_kcal * 1.10:
                pdf.set_fill_color(16, 185, 129)
            else:
                pdf.set_fill_color(239, 68, 68)
            pdf.rect(bx, by, bar_w, bh, "F")

        # Etiqueta de semana en eje X
        step = 1 if n_bars <= 16 else 4
        if i % step == 0 or i == n_bars - 1:
            pdf.set_font("helvetica", "", 5.5)
            pdf.set_text_color(100, 116, 139)
            pdf.set_xy(bx - 3, plot_y + plot_h + 1)
            pdf.cell(bar_w + 6, 4, w["short_label"], align="C")

    pdf.set_y(chart_y + chart_h + 4)

    # Tabla desglosada Semana a Semana
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, "2. DESGLOSE SEMANA POR SEMANA (MEDIA DIARIA Y PESO)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    col_w = [38, 16, 20, 24, 18, 18, 18, 20, 18]
    headers = ["Semana (Lun-Dom)", "Días", "Kcal/día", "Déficit/día", "Prot (g)", "Carbs (g)", "Grasa (g)", "Peso Med.", "Var. Peso"]

    def print_week_header():
        pdf.set_font("helvetica", "B", 7.5)
        pdf.set_fill_color(15, 23, 42)
        pdf.set_text_color(255, 255, 255)
        for cw, h_txt in zip(col_w, headers):
            pdf.cell(cw, 6, h_txt, border=1, fill=True, align="C")
        pdf.ln()

    print_week_header()
    fill = False

    for w in reversed(weeks):
        if pdf.get_y() > 270:
            pdf.add_page()
            print_week_header()

        pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(30, 41, 59)
        rh = 5.2

        has = w["logged_days"] > 0
        kcal_s = f"{w['kcal']:.0f}" if has else "-"
        def_s = (f"-{w['avg_deficit']:.0f} kcal" if w["avg_deficit"] > 0 else f"+{abs(w['avg_deficit']):.0f} kcal") if has else "-"
        p_s = f"{w['protein']:.1f}" if has else "-"
        c_s = f"{w['carbs']:.1f}" if has else "-"
        f_s = f"{w['fat']:.1f}" if has else "-"
        w_s = f"{w['avg_weight']:.1f} kg" if w["avg_weight"] is not None else "-"
        wd_s = f"{w['weight_diff']:+.1f} kg" if w["weight_diff"] is not None else "-"

        pdf.cell(col_w[0], rh, w["label"], border=1, fill=fill, align="L")
        pdf.cell(col_w[1], rh, f"{w['logged_days']}/7", border=1, fill=fill, align="C")
        pdf.cell(col_w[2], rh, kcal_s, border=1, fill=fill, align="R")

        if has and w["avg_deficit"] > 0:
            pdf.set_text_color(16, 185, 129)
        elif has:
            pdf.set_text_color(239, 68, 68)
        else:
            pdf.set_text_color(140, 140, 140)
        pdf.cell(col_w[3], rh, def_s, border=1, fill=fill, align="R")

        pdf.set_text_color(30, 41, 59)
        pdf.cell(col_w[4], rh, p_s, border=1, fill=fill, align="R")
        pdf.cell(col_w[5], rh, c_s, border=1, fill=fill, align="R")
        pdf.cell(col_w[6], rh, f_s, border=1, fill=fill, align="R")

        pdf.set_font("helvetica", "B" if w["avg_weight"] else "", 7.5)
        pdf.set_text_color(37, 99, 235) if w["avg_weight"] else pdf.set_text_color(140, 140, 140)
        pdf.cell(col_w[7], rh, w_s, border=1, fill=fill, align="C")

        pdf.set_font("helvetica", "", 7.5)
        if w["weight_diff"] is not None:
            pdf.set_text_color(16, 185, 129) if w["weight_diff"] <= 0 else pdf.set_text_color(239, 68, 68)
        else:
            pdf.set_text_color(140, 140, 140)
        pdf.cell(col_w[8], rh, wd_s, border=1, fill=fill, align="C")

        pdf.ln()
        fill = not fill

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()

