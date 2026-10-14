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
            # Color de barra: Verde si en objetivo o debajo, Rojo si superó objetivo
            if k <= goal_kcal:
                pdf.set_fill_color(16, 185, 129)  # Verde esmeralda
                pdf.set_draw_color(13, 148, 136)
            else:
                pdf.set_fill_color(239, 68, 68)   # Rojo / exceso
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

    # Verde: en objetivo
    pdf.set_fill_color(16, 185, 129)
    pdf.rect(leg_x, leg_y + 1, 3.5, 3.5, "F")
    pdf.set_xy(leg_x + 5, leg_y)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(38, 5, "En objetivo / Déficit")

    # Rojo: superó
    leg_x2 = leg_x + 44
    pdf.set_fill_color(239, 68, 68)
    pdf.rect(leg_x2, leg_y + 1, 3.5, 3.5, "F")
    pdf.set_xy(leg_x2 + 5, leg_y)
    pdf.cell(34, 5, "Superó objetivo")

    # Gris: sin registro
    leg_x3 = leg_x2 + 40
    pdf.set_fill_color(226, 232, 240)
    pdf.rect(leg_x3, leg_y + 1, 3.5, 3.5, "F")
    pdf.set_xy(leg_x3 + 5, leg_y)
    pdf.cell(30, 5, "Sin registro")

    # Naranja: Línea objetivo
    leg_x4 = leg_x3 + 36
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
            # Color de progreso
            if d["kcal"] <= goal_kcal:
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
