from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.colors import HexColor, black, lightgrey, grey, white
import datetime
import uuid
from typing import List, Dict, Any, Optional


from pydantic import BaseModel, Field, RootModel, AliasChoices
from typing import List, Literal, Optional

class ChecklistItem(BaseModel):
    ChecklistName: str
    ChecklistSerialNo: int
    ChecklistId: str
    ChecklistType: Literal["Pass/Fail", "Yes/No", "Okay/Not Okay"]

class ChecklistGroup(BaseModel):
    GroupName: str
    GroupId: str
    SerialNo: int
    Checklist: List[ChecklistItem]

class FullChecklist(RootModel[List[ChecklistGroup]]):
    pass

def generate_inspection_pdf(
    user_name: str,
    user_email: str,
    vehicle_plate_number: str,
    checklist_data: FullChecklist,
    submitted_form_data: Dict[str, str],
    trip_advice_content: str,
    file_name: str = "Inspection_Report.pdf",
    comments_analysis_text: str = "No additional comments or analysis provided for this inspection."
) -> Optional[str]:
    """
    Generates a PDF inspection report with improved visual styling and a footer.
    """
    # --- Generate Inspection ID once for the report ---
    report_inspection_id = str(uuid.uuid4())

    doc = SimpleDocTemplate(file_name, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Define custom styles for better control
    styles.add(ParagraphStyle(name='CenteredTitle', parent=styles['h1'], alignment=TA_CENTER, fontSize=20, leading=24, spaceAfter=12))
    styles.add(ParagraphStyle(name='CompanyName', parent=styles['h2'], alignment=TA_CENTER, fontSize=16, leading=18, spaceAfter=6, textColor=HexColor('#333333')))
    styles.add(ParagraphStyle(name='SectionHeader', parent=styles['h2'], alignment=TA_LEFT, fontSize=14, leading=16, spaceBefore=10, spaceAfter=8, textColor=HexColor('#333333')))
    styles.add(ParagraphStyle(name='TableCaption', parent=styles['h3'], alignment=TA_LEFT, fontSize=10, leading=12, spaceAfter=6))
    styles.add(ParagraphStyle(name='NormalSmall', parent=styles['Normal'], fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='NormalBold', parent=styles['Normal'], fontSize=10, leading=12, fontName='Helvetica-Bold'))
    
    # --- Refined Advice Headers with explicit bold font and adjusted spacing ---
    styles.add(ParagraphStyle(name='AdviceHeader', parent=styles['h2'], alignment=TA_LEFT, fontSize=16, leading=18, spaceBefore=0, spaceAfter=10, textColor=HexColor('#CC0000'), fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='AdviceHeaderGreen', parent=styles['h2'], alignment=TA_LEFT, fontSize=16, leading=18, spaceBefore=0, spaceAfter=10, textColor=HexColor('#008000'), fontName='Helvetica-Bold'))
    # Style for the actual advice body, including list items
    styles.add(ParagraphStyle(name='AdviceBody', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6, bulletIndent=18))

    def footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 9) # Set font for footer text
        
        # Text for Inspection ID (left-aligned)
        id_text = f"Inspection ID: {report_inspection_id}"
        canvas_obj.drawString(doc_obj.leftMargin, 0.5 * inch, id_text) # Position 0.5 inch from bottom
        
        # Text for Inspector Name (right-aligned)
        name_text = "Inspector Name: Prof. E"
        text_width = canvas_obj.stringWidth(name_text, 'Helvetica', 9)
        # Position at (document_width + left_margin - text_width) to right-align
        canvas_obj.drawString(doc_obj.width + doc_obj.leftMargin - text_width, 0.5 * inch, name_text)
        
        canvas_obj.restoreState()

    # --- Header Section ---
    try:
        # Assuming you have a logo file. Adjust path and size as needed.
        # logo = Image("path/to/your/gamanda_logo.png", width=1.5*inch, height=0.5*inch)
        # elements.append(logo)
        # elements.append(Spacer(1, 0.1 * inch))
        pass
    except FileNotFoundError:
        print("Logo image not found. Skipping logo.")
    except Exception as e:
        print(f"Error loading logo: {e}. Skipping logo.")

    elements.append(Paragraph("Camanda", styles['CompanyName']))
    elements.append(Paragraph("VEHICLE INSPECTION REPORT", styles['CenteredTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    # --- Top Information Table ---
    report_date = datetime.datetime.now().strftime("%Y-%m-%d")

    # Example values for mileage and inspection date if not in input
    mileage = "N/A" # You might get this from another input field
    inspection_date = report_date # Using report date for now

    info_data = [
        [Paragraph("Vehicle No.", styles['NormalBold']), Paragraph(vehicle_plate_number, styles['Normal']),
         Paragraph("Driver's Name", styles['NormalBold']), Paragraph(user_name, styles['Normal'])],
        [Paragraph("Mileage", styles['NormalBold']), Paragraph(mileage, styles['Normal']),
         Paragraph("Inspection Date", styles['NormalBold']), Paragraph(inspection_date, styles['Normal'])],
    ]

    info_table_style = TableStyle([
        ('TEXTCOLOR', (0,0), (-1,-1), black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'), # Bold first column
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'), # Bold third column
        ('GRID', (0,0), (-1,-1), 0.5, HexColor('#CCCCCC')), # Grey grid lines
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ])

    col_widths_info = [1.2 * inch, 2.0 * inch, 1.2 * inch, 2.0 * inch]
    info_table = Table(info_data, colWidths=col_widths_info)
    info_table.setStyle(info_table_style)
    elements.append(info_table)
    elements.append(Spacer(1, 0.2 * inch))


    elements.append(Paragraph("Inspection Details", styles['SectionHeader']))
    elements.append(Spacer(1, 0.1 * inch))

    # --- Inspection Details (Checklist Groups and Items) ---
    for group in checklist_data.root:
        elements.append(Paragraph(f"Group: {group.GroupName}", styles['SectionHeader']))
        elements.append(Spacer(1, 0.05 * inch))

        # Prepare data for the group's table
        group_table_data = [[
            Paragraph("Item", styles['NormalBold']),
            Paragraph("Status", styles['NormalBold'])
        ]] # Header row

        for item in group.Checklist:
            item_status = submitted_form_data.get(item.ChecklistId, "No selection made")
            
            # Format "No selection made" for better readability in the PDF
            display_status = item_status if item_status is not None else "Not Inspected"

            group_table_data.append([
                Paragraph(item.ChecklistName, styles['Normal']),
                Paragraph(display_status, styles['Normal'])
            ])

        # Define table style for inspection items
        inspection_table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), HexColor('#E0E0E0')), # Light grey for header row
            ('TEXTCOLOR', (0,0), (-1,0), black),
            ('BACKGROUND', (0,1), (-1,-1), white), # Explicitly set data row background to white
            ('ALIGN', (0,0), (0,-1), 'LEFT'), # Item column left aligned
            ('ALIGN', (1,0), (1,-1), 'CENTER'), # Status column center aligned
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('GRID', (0,0), (-1,-1), 0.5, HexColor('#CCCCCC')), # Lighter grey grid lines, thinner
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ])

        # Column widths for Item and Status
        col_widths_inspection = [4.5 * inch, 1.5 * inch]
        group_table = Table(group_table_data, colWidths=col_widths_inspection)
        group_table.setStyle(inspection_table_style)
        elements.append(group_table)
        elements.append(Spacer(1, 0.2 * inch))

    # --- Trip Advice Summary ---
    elements.append(PageBreak())
    elements.append(Spacer(1, 0.4 * inch))
    elements.append(Paragraph("Trip Advice Summary", styles['SectionHeader']))
    elements.append(Spacer(1, 0.1 * inch))

    advice_lines = trip_advice_content.split('\n')
    for line in advice_lines:
        if line.strip():
            if line.startswith("## "):
                display_text = line[3:]
                if "All Clear" in display_text:
                    elements.append(Paragraph(display_text, styles['AdviceHeaderGreen']))
                else:
                    elements.append(Paragraph(display_text, styles['AdviceHeader']))
            elif line.startswith("- "):
                elements.append(Paragraph(line, styles['AdviceBody']))
            else:
                elements.append(Paragraph(line, styles['AdviceBody']))
    
    elements.append(Spacer(1, 0.2 * inch))

    # --- Comments & Analysis Section ---
    elements.append(Paragraph("Comments & Analysis", styles['SectionHeader']))
    elements.append(Spacer(1, 0.1 * inch))
    comments_lines = comments_analysis_text.split('\n')
    for line in comments_lines:
        if line.strip():
            elements.append(Paragraph(line, styles['Normal']))
    elements.append(Spacer(1, 0.2 * inch))


    try:
        # --- Pass the footer function to doc.build() ---
        doc.build(elements, onFirstPage=footer, onLaterPages=footer)
        return file_name
    except Exception as e:
        print(f"Error building PDF: {e}")
        return None