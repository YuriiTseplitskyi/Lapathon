import os
import math
from datetime import datetime
from fpdf import FPDF
from app.models.domain import PersonProfile
from app.core.settings import settings
import config

class PDFReport(FPDF):
    def __init__(self):
        super().__init__()
        self.main_font = 'DejaVu'
        font_path = os.path.join(config.FONTS_DIR, settings.FONT_FILENAME)
        
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Шрифт не знайдено: {font_path}")
        
        self.add_font(self.main_font, '', font_path)
        self.add_font(self.main_font, 'B', font_path)
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font(self.main_font, '', 9)
        current_date = datetime.now().strftime("%d.%m.%Y")
        self.cell(0, 5, f"станом на {current_date}", 0, 1, 'R')
        
        self.set_draw_color(0, 51, 102)
        self.line(10, 26, 200, 26)
        self.ln(5)

    def section_header(self, title):
        self.ln(3)
        self.set_font(self.main_font, 'B', 11)
        self.set_fill_color(230, 235, 245)
        self.cell(0, 9, f" {title.upper()}", 0, 1, 'L', True)
        self.ln(2)

    def draw_table_header(self, headers, widths):
        self.set_font(self.main_font, 'B', 9)
        self.set_fill_color(210, 210, 210)
        for i, h in enumerate(headers):
            self.cell(widths[i], 8, h, 1, 0, 'C', True)
        self.ln()

    def info_row(self, label, value):
        self.set_font(self.main_font, 'B', 10)
        self.cell(55, 7, f"{label}:", 0, 0)
        self.set_font(self.main_font, '', 10)
        self.cell(0, 7, str(value if value else "---"), 0, 1)

    def smart_row(self, data, widths, alignments=None):
        """Малює рядок таблиці з ідеально рівними клітинками"""
        if not alignments:
            alignments = ['L'] * len(widths)
        
        line_height = 5 
        max_lines = 1
        for i, text in enumerate(data):
            lines = self.multi_cell(widths[i], line_height, str(text), split_only=True)
            max_lines = max(max_lines, len(lines))
        
        total_row_height = max(8, max_lines * line_height)
        
        if self.get_y() + total_row_height > self.page_break_trigger:
            self.add_page()

        start_x = self.get_x()
        start_y = self.get_y()
        
        for i, text in enumerate(data):
            self.set_xy(start_x, start_y)
            self.cell(widths[i], total_row_height, "", 1, 0)
            self.set_xy(start_x, start_y)
            self.multi_cell(widths[i], line_height, str(text), 0, alignments[i])
            start_x += widths[i]
        
        self.set_xy(self.l_margin, start_y + total_row_height)

def generate_pdf(profile: PersonProfile) -> str:
    pdf = PDFReport()
    pdf.add_page()

    # 1. ЗАГАЛЬНА ІНФОРМАЦІЯ
    pdf.section_header("Загальна інформація")
    personal_data = [
        ("Прізвище", profile.last_name),
        ("Ім'я", profile.first_name),
        ("По батькові", profile.middle_name),
        ("Дата народження", profile.birth_date),
        ("Стать", profile.gender),
        ("РНОКПП", profile.rnokpp),
        ("УНЗР", profile.unzr),
        ("Громадянство", profile.citizenship),
    ]
    for label, val in personal_data:
        pdf.info_row(label, val)

    # 2. ІСТОРІЯ ПІБ (в нас такого ніби поки не було, але на прикладі було)
    if profile.name_history:
        pdf.section_header("Колишні ПІБ")
        w = [90, 40, 60]
        pdf.draw_table_header(["ПІБ", "Дата події", "Джерело/Тип"], w)
        pdf.set_font(pdf.main_font, '', 9)
        for h in profile.name_history:
            pdf.smart_row([h.old_name, h.event_date, h.event_type], w)

    # 3. РОДИНА
    if profile.family:
        pdf.section_header("Родинні зв'язки")
        w = [65, 20, 25, 80]
        pdf.draw_table_header(["ПІБ", "Роль", "РНОКПП", "Джерело / Орган"], w)
        pdf.set_font(pdf.main_font, '', 9)
        for rel in profile.family:
            pdf.smart_row([rel.full_name, rel.role_str, rel.rnokpp or "---", rel.registry_office], w)

    # 4. НЕРУХОМІСТЬ
    if profile.properties:
        pdf.section_header("Об'єкти нерухомого майна")
        w = [35, 95, 30, 30]
        pdf.draw_table_header(["Тип", "Адреса", "Площа", "Частка"], w)
        pdf.set_font(pdf.main_font, '', 8)
        for p in profile.properties:
            area_text = f"{p.area} {p.area_unit}" if p.area else "---"
            pdf.smart_row([p.re_type, p.address, area_text, p.share], w)

    # 5. ТРАНСПОРТ
    if profile.vehicles:
        pdf.section_header("Транспортні засоби")
        w = [65, 15, 40, 35, 35]
        pdf.draw_table_header(["Марка / Модель", "Рік", "Держномер", "Колір", "Роль"], w)
        pdf.set_font(pdf.main_font, '', 9)
        for v in profile.vehicles:
            brand = f"{v.make} {v.model}".strip() or "ТЗ"
            role = getattr(v, 'role', 'Власник')
            pdf.smart_row([brand, v.year or "н/д", v.registration_number, v.color or "---", role], w, ['L','C','C','C','L'])

    # 6. АДРЕСИ
    if profile.addresses:
        pdf.section_header("Пов'язані адреси")
        w = [40, 80, 35, 35]
        pdf.draw_table_header(["Регіон", "Вулиця", "Буд.", "Кв."], w)
        pdf.set_font(pdf.main_font, '', 9)
        for addr in profile.addresses:
            pdf.smart_row([addr.region, f"вул. {addr.street or '---'}", addr.house, addr.appartment or "---"], w)

    # 7. КОМПАНІЇ ТА ДОХОДИ
    if profile.companies:
        pdf.section_header("Доходи від організацій (сумарно)")
        w = [100, 40, 50]
        pdf.draw_table_header(["Назва організації", "ЄДРПОУ", "Сума прибутку"], w)
        pdf.set_font(pdf.main_font, '', 9)
        for comp in profile.companies:
            amount = f"{comp.total_amount:,.2f}".replace(',', ' ') + " грн"
            pdf.smart_row([comp.name, comp.edrpou, amount], w, ['L', 'C', 'R'])

    # 8. СУДОВІ СПРАВИ (поки немає, бо загубились звʼязки)
    if profile.court_cases:
        pdf.section_header("Судові справи та рішення")
        for c in profile.court_cases:
            pdf.set_font(pdf.main_font, 'B', 9)
            pdf.multi_cell(0, 6, f"Справа №{c.case_num} — {c.court_name}", 'LTR', 'L')
            pdf.set_font(pdf.main_font, '', 9)
            pdf.multi_cell(0, 6, f"Рішення: {c.decision_type} від {c.decision_date}", 'LBR', 'L')
            pdf.ln(2)

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    output_path = os.path.join(config.REPORTS_DIR, f"{profile.rnokpp}.pdf")
    pdf.output(output_path)
    return output_path