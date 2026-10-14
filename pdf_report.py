"""Generador de informes PDF para la Calculadora de Macros usando fpdf2."""
import io
from datetime import date, datetime
from fpdf import FPDF, XPos, YPos


class MacroPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_title("Informe Nutricional - Calculadora de Macros")
        self.set_author("Calculadora de Macros")

    def header(self):
        # Franja superior verde esmeralda
        self.set_fill_color(16, 185, 129)
        self.rect(0, 0, 210, 6, "F")
        self.set_y(10)

    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Calculadora de Macros · Página {self.page_no()}/{{nb}}", align="C")


def generate_macro_pdf(conn, target_date=None, days_range=7):
    """Genera un archivo PDF binario con el informe nutricional, métricas biométricas y desglose de comidas."""
    target_date = target_date or date.today().isoformat()
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

    # Leer entradas del día
    entries = conn.execute(
        "SELECT * FROM entries WHERE date=? ORDER BY time, id", (target_date,)
    ).fetchall()
    day_entries = [dict(e) for e in entries]

    tot_kcal = sum(e["kcal"] for e in day_entries)
    tot_p = sum(e["protein"] for e in day_entries)
    tot_c = sum(e["carbs"] for e in day_entries)
    tot_f = sum(e["fat"] for e in day_entries)
    actual_deficit = tdee - tot_kcal

    # Leer histórico
    hist_rows = conn.execute(
        "SELECT date, ROUND(SUM(kcal),1) kcal, ROUND(SUM(protein),1) protein, "
        "ROUND(SUM(carbs),1) carbs, ROUND(SUM(fat),1) fat, COUNT(*) n "
        "FROM entries WHERE date >= date(?, ?) "
        "GROUP BY date ORDER BY date DESC",
        (target_date, f"-{days_range - 1} days"),
    ).fetchall()
    hist_days = [dict(r) for r in hist_rows]
    avg_kcal = (sum(r["kcal"] for r in hist_days) / len(hist_days)) if hist_days else 0.0
    avg_p = (sum(r["protein"] for r in hist_days) / len(hist_days)) if hist_days else 0.0
    avg_c = (sum(r["carbs"] for r in hist_days) / len(hist_days)) if hist_days else 0.0
    avg_f = (sum(r["fat"] for r in hist_days) / len(hist_days)) if hist_days else 0.0

    # Leer pesos recientes
    weights_rows = conn.execute("SELECT date, kg FROM weights ORDER BY date DESC LIMIT 5").fetchall()
    recent_weights = [dict(w) for w in weights_rows]

    pdf = MacroPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # Título principal
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 9, "INFORME NUTRICIONAL & MACROS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 5, f"Fecha analizada: {target_date}   |   Generado el {now_str}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # ----------------------------------------------------
    # SECCIÓN 1: Perfil y Parámetros Biométricos
    # ----------------------------------------------------
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, pdf.get_y(), 190, 36, "DF")

    pdf.set_xy(14, pdf.get_y() + 3)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(0, 5, "OBJETIVOS Y PARÁMETROS BIOMÉTRICOS DEL USUARIO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.set_x(14)
    line1 = (
        f"- Gasto Calorico (TDEE): {tdee:.0f} kcal   |   "
        f"Objetivo Diario: {goal_kcal:.0f} kcal   |   "
        f"Deficit Planificado: -{planned_deficit:.0f} kcal/dia"
    )
    pdf.cell(0, 5, line1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(14)
    line2 = (
        f"- Peso: {weight:.1f} kg   |   "
        f"Masa Magra (LBM): {lbm:.1f} kg   |   "
        f"Grasa Estimada: {fat_mass:.1f} kg ({fat_pct:.1f}%)"
    )
    pdf.cell(0, 5, line2, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(14)
    line3 = (
        f"- Macros Objetivo: {goal_p:.0f}g Proteina ({prot_per_lbm:.2f} g/kg LBM)   |   "
        f"{goal_c:.0f}g Carbohidratos   |   {goal_f:.0f}g Grasas"
    )
    pdf.cell(0, 5, line3, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(14)
    pdf.set_font("helvetica", "I", 8.5)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(
        0, 5,
        "Nota: Deficit enfocado en perdida de grasa manteniendo masa magra con alta ingesta de proteina.",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.ln(6)

    # ----------------------------------------------------
    # SECCIÓN 2: Resumen del Día vs Objetivos
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, f"Resumen Diario ({target_date})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    # 4 Tarjetas de métricas diarias
    card_w = 45
    card_h = 22
    y_start = pdf.get_y()

    cards = [
        ("Calorias Ingeridas", f"{tot_kcal:.0f} kcal", f"Obj: {goal_kcal:.0f} kcal", (249, 115, 22)),
        ("Deficit Real vs TDEE", f"-{actual_deficit:.0f} kcal", f"TDEE: {tdee:.0f} kcal", (16, 185, 129)),
        ("Proteina Total", f"{tot_p:.1f} g", f"Obj: {goal_p:.0f} g", (37, 99, 235)),
        ("Hidratos / Grasa", f"{tot_c:.0f}g / {tot_f:.0f}g", f"Obj: {goal_c:.0f}g / {goal_f:.0f}g", (217, 119, 6)),
    ]

    for idx, (title, val, sub, col) in enumerate(cards):
        x = 10 + idx * 48
        pdf.set_xy(x, y_start)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(x, y_start, card_w, card_h, "DF")

        pdf.set_xy(x + 2, y_start + 2)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(card_w - 4, 4, title, align="C")

        pdf.set_xy(x + 2, y_start + 7)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(*col)
        pdf.cell(card_w - 4, 7, val, align="C")

        pdf.set_xy(x + 2, y_start + 15)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(card_w - 4, 4, sub, align="C")

    pdf.set_y(y_start + card_h + 5)

    # ----------------------------------------------------
    # SECCIÓN 3: Detalle de Alimentos y Comidas
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, "Detalle de Comidas Registradas", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    if not day_entries:
        pdf.set_font("helvetica", "I", 10)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 8, "No hay comidas registradas para este dia.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)
    else:
        # Cabecera de la tabla
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 8.5)

        col_w = [25, 75, 22, 20, 16, 16, 16]
        headers = ["Comida", "Alimento / Combo", "Cantidad", "Kcal", "Prot (g)", "Hidr (g)", "Grasa (g)"]
        for w, h in zip(col_w, headers):
            pdf.cell(w, 6, h, border=1, fill=True, align="C")
        pdf.ln()

        # Filas
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(30, 41, 59)
        fill = False

        for e in day_entries:
            pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
            meal_txt = (e.get("meal") or "otro").capitalize()
            name_txt = (e.get("name") or "")[:40]
            grams_txt = f"{e['grams']:.0f} g" if e.get("grams") else ("Solo kcal" if e.get("kind") == "quick" else "-")
            kcal_txt = f"{e['kcal']:.0f}"
            p_txt = f"{e['protein']:.1f}"
            c_txt = f"{e['carbs']:.1f}"
            f_txt = f"{e['fat']:.1f}"

            pdf.cell(col_w[0], 6, meal_txt, border=1, fill=fill, align="L")
            pdf.cell(col_w[1], 6, name_txt, border=1, fill=fill, align="L")
            pdf.cell(col_w[2], 6, grams_txt, border=1, fill=fill, align="C")
            pdf.cell(col_w[3], 6, kcal_txt, border=1, fill=fill, align="R")
            pdf.cell(col_w[4], 6, p_txt, border=1, fill=fill, align="R")
            pdf.cell(col_w[5], 6, c_txt, border=1, fill=fill, align="R")
            pdf.cell(col_w[6], 6, f_txt, border=1, fill=fill, align="R")
            pdf.ln()
            fill = not fill

        # Fila de totales
        pdf.set_font("helvetica", "B", 8.5)
        pdf.set_fill_color(241, 245, 249)
        pdf.cell(col_w[0] + col_w[1] + col_w[2], 6, "TOTAL DEL DIA", border=1, fill=True, align="R")
        pdf.cell(col_w[3], 6, f"{tot_kcal:.0f}", border=1, fill=True, align="R")
        pdf.cell(col_w[4], 6, f"{tot_p:.1f}", border=1, fill=True, align="R")
        pdf.cell(col_w[5], 6, f"{tot_c:.1f}", border=1, fill=True, align="R")
        pdf.cell(col_w[6], 6, f"{tot_f:.1f}", border=1, fill=True, align="R")
        pdf.ln(8)

    # ----------------------------------------------------
    # SECCIÓN 4: Histórico y Promedios del Periodo
    # ----------------------------------------------------
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, f"Evolucion y Promedios (Ultimos {days_range} dias)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, pdf.get_y(), 190, 24, "DF")

    pdf.set_xy(14, pdf.get_y() + 3)
    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(30, 41, 59)

    h_line1 = (
        f"- Dias con registros en periodo: {len(hist_days)} de {days_range}   |   "
        f"Promedio calorico diario: {avg_kcal:.0f} kcal   |   "
        f"Deficit medio: -{(tdee - avg_kcal):.0f} kcal/dia"
    )
    pdf.cell(0, 5, h_line1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(14)
    h_line2 = (
        f"- Promedios de macros: {avg_p:.1f}g Proteina   |   "
        f"{avg_c:.1f}g Carbohidratos   |   {avg_f:.1f}g Grasas"
    )
    pdf.cell(0, 5, h_line2, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if recent_weights:
        pdf.set_x(14)
        w_str = ", ".join([f"{w['date']}: {w['kg']:.1f} kg" for w in recent_weights[:3]])
        pdf.cell(0, 5, f"- Ultimos pesos registrados: {w_str}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Generar bytes de salida
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
