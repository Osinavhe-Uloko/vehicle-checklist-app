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
    file_name: str = "Inspection_Report.pdf"
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
    styles.add(ParagraphStyle(name='CenteredTitle', parent=styles['h1'], alignment=TA_CENTER, fontSize=20, leading=24, spaceAfter=12, textColor=HexColor('#1F3A93')))
    styles.add(ParagraphStyle(name='CompanyName', parent=styles['h2'], alignment=TA_CENTER, fontSize=16, leading=18, spaceAfter=6, textColor=HexColor('#333333')))
    styles.add(ParagraphStyle(name='SectionHeader', parent=styles['h2'], alignment=TA_LEFT, fontSize=14, leading=16, spaceBefore=10, spaceAfter=8, textColor=HexColor('#1F3A93')))
    styles.add(ParagraphStyle(name='TableCaption', parent=styles['h3'], alignment=TA_LEFT, fontSize=10, leading=12, spaceAfter=6))
    styles.add(ParagraphStyle(name='NormalSmall', parent=styles['Normal'], fontSize=10, leading=12, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='NormalBold', parent=styles['Normal'], fontSize=10, leading=12, fontName='Helvetica-Bold', textColor=HexColor('#1F3A93')))
    
    # --- Refined Advice Headers with explicit bold font and adjusted spacing ---
    styles.add(ParagraphStyle(name='AdviceHeader', parent=styles['h2'], alignment=TA_LEFT, fontSize=16, leading=18, spaceBefore=0, spaceAfter=10, textColor=HexColor('#CC0000'), fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='AdviceHeaderGreen', parent=styles['h2'], alignment=TA_LEFT, fontSize=16, leading=18, spaceBefore=0, spaceAfter=10, textColor=HexColor('#008000'), fontName='Helvetica-Bold'))
    # Style for the actual advice body, including list items
    styles.add(ParagraphStyle(name='AdviceBody', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6, bulletIndent=18))

    # Add specific styles for Pass, Fail, Skipped results in tables
    styles.add(ParagraphStyle(name='Pass', fontSize=10, leading=12, fontName='Helvetica-Bold', textColor=HexColor('#006400')))  # Dark Green
    styles.add(ParagraphStyle(name='Fail', fontSize=10, leading=12, fontName='Helvetica-Bold', textColor=HexColor('#8B0000')))  # Dark Red
    styles.add(ParagraphStyle(name='Skipped', fontSize=10, leading=12, fontName='Helvetica-Bold', textColor=HexColor('#FFA500'))) # Orange

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
        [Paragraph("Vehicle No.", styles['NormalSmall']), Paragraph(vehicle_plate_number, styles['Normal']),
         Paragraph("Driver's Name", styles['NormalSmall']), Paragraph(user_name, styles['Normal'])],
        [Paragraph("Mileage", styles['NormalSmall']), Paragraph(mileage, styles['Normal']),
         Paragraph("Inspection Date", styles['NormalSmall']), Paragraph(inspection_date, styles['Normal'])],
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

    # --- Inspection Summary ---
    elements.append(Paragraph("Inspection Summary", styles['SectionHeader']))
    elements.append(Spacer(1, 0.1 * inch))

    # --- New: Group Pass Rate Table ---
    group_pass_rate_data = _calculate_group_pass_rates(checklist_data, submitted_form_data)

    # Table header
    group_table_data = [[
        Paragraph("Section", styles['NormalBold']),
        Paragraph("Pass Rate", styles['NormalBold'])
    ]]
    
    # Add group data
    for group_summary in group_pass_rate_data:
        group_table_data.append([
            Paragraph(group_summary['GroupName'], styles['Normal']),
            Paragraph(group_summary['PassRate'], styles['Normal'])
        ])

    group_pass_table_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#E0E0E0')), # Header background
        ('TEXTCOLOR', (0,0), (-1,0), black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('GRID', (0,0), (-1,-1), 0.5, HexColor('#CCCCCC')),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ])

    group_pass_rate_table = Table(group_table_data, colWidths=[3.5*inch, 2.5*inch])
    group_pass_rate_table.setStyle(group_pass_table_style)
    elements.append(group_pass_rate_table)
    elements.append(Spacer(1, 0.2 * inch)) # Spacer after group table

    # --- Existing: Overall Inspection Summary (Total Items, Passed, Failed, Skipped) ---
    summary_percentages = _calculate_summary_percentages(checklist_data, submitted_form_data)
    
    # Data for the overall summary table
    summary_data = [
        [Paragraph("Total Items Inspected:", styles['NormalBold']), Paragraph(str(summary_percentages['total_items']), styles['Normal'])],
        [Paragraph("Items Passed:", styles['NormalBold']), Paragraph(f"{summary_percentages['passed_count']} ({summary_percentages['passed_percentage']:.2f}%)", styles['Pass'])],
        [Paragraph("Items Failed:", styles['NormalBold']), Paragraph(f"{summary_percentages['failed_count']} ({summary_percentages['failed_percentage']:.2f}%)", styles['Fail'])],
        [Paragraph("Items Skipped:", styles['NormalBold']), Paragraph(f"{summary_percentages['skipped_count']} ({summary_percentages['skipped_percentage']:.2f}%)", styles['Skipped'])]
    ]

    summary_table_style = TableStyle([
        ('TEXTCOLOR', (0,0), (-1,-1), HexColor('#1F3A93')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('GRID', (0,0), (-1,-1), 0.5, HexColor('#CCCCCC')),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ])

    summary_table = Table(summary_data, colWidths=[2.5*inch, 3.5*inch])
    summary_table.setStyle(summary_table_style)
    elements.append(summary_table)
    elements.append(Spacer(1, 0.2 * inch))


    elements.append(Paragraph("Inspection Details", styles['SectionHeader']))
    elements.append(Spacer(1, 0.07 * inch))

    # --- Inspection Details (Checklist Groups and Items) ---
    for group in checklist_data.root:
        elements.append(Paragraph(f"{group.GroupName}", styles['SectionHeader']))
        elements.append(Spacer(1, 0.05 * inch))

        # Prepare data for the group's table
        group_table_data = [[
            Paragraph("Item", styles['NormalBold']),
            Paragraph("Status", styles['NormalBold'])
        ]] # Header row

        for item in group.Checklist:
            unique_id = f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}"
            # Get the raw user input, strip whitespace, but keep original casing for display
            # item_status = submitted_form_data.get(unique_id, "No selection made")
            
            raw_item_status = submitted_form_data.get(unique_id)
            if raw_item_status is None:
                item_status = "No selection made" # Display as string
            else:
                item_status = str(raw_item_status) # Ensure it's a string for display
            
            # display_status is now redundant if item_status is always a string
            display_status = item_status 
            # Format "No selection made" for better readability in the PDF
            # display_status = item_status if item_status is not None else "Not Inspected"
            
            group_table_data.append([
                Paragraph(item.ChecklistName, styles['Normal']),
                Paragraph(display_status, styles['Normal'])
            ])

        # Define table style for inspection items
        inspection_table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), white), # Light grey for header row
            ('TEXTCOLOR', (0,0), (-1,0), HexColor('#1F3A93')),
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

    # # --- Trip Advice Summary ---
    # # elements.append(PageBreak())
    # elements.append(Spacer(1, 0.4 * inch))
    # elements.append(Paragraph("Trip Advice Summary", styles['SectionHeader']))
    # elements.append(Spacer(1, 0.1 * inch))

    # advice_lines = trip_advice_content.split('\n')
    # for line in advice_lines:
    #     if line.strip():
    #         if line.startswith("## "):
    #             display_text = line[3:]
    #             if "All Clear" in display_text:
    #                 elements.append(Paragraph(display_text, styles['AdviceHeaderGreen']))
    #             else:
    #                 elements.append(Paragraph(display_text, styles['AdviceHeader']))
    #         elif line.startswith("- "):
    #             elements.append(Paragraph(line, styles['AdviceBody']))
    #         else:
    #             elements.append(Paragraph(line, styles['AdviceBody']))
    
    # elements.append(Spacer(1, 0.2 * inch))

    # --- Comments & Analysis Section (Dynamically Generated) ---
    elements.append(Paragraph("Comments & Analysis", styles['SectionHeader']))
    elements.append(Spacer(1, 0.1 * inch))
    # Dynamically generate comments_analysis_text
    comments_and_analysis_flowables = _generate_comments_and_analysis(summary_percentages, trip_advice_content)
    elements.extend(comments_and_analysis_flowables) # Extend the main elements list with these flowables
    # for line in comments_lines:
    #     if line.strip():
    #         # Apply Normal style for comments, bolding will be handled by HTML tags in the text
    #         elements.append(Paragraph(line, styles['Normal']))
    # elements.append(Spacer(1, 0.2 * inch))


    try:
        # --- Pass the footer function to doc.build() ---
        doc.build(elements, onFirstPage=footer, onLaterPages=footer)
        return file_name
    except Exception as e:
        print(f"Error building PDF: {e}")
        return None

def _calculate_summary_percentages(checklist_data: FullChecklist, submitted_form_data: Dict[str, Any]) -> Dict[str, Any]: # Changed return type to Any for list of items
    total_items = 0
    passed_count = 0
    failed_count = 0
    skipped_count = 0
    items_requiring_attention = []

    for group in checklist_data.root:
        for item in group.Checklist:
            total_items += 1
            unique_id = f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}"
            # Ensure result is stripped and lowercased for robust comparison
            # result = submitted_form_data.get(unique_id, "No selection made").strip().lower() 
            raw_result = submitted_form_data.get(unique_id)
            
            result = "no selection made" # Default assignment
            
            if raw_result is None:
                result = "no selection made"
            else:
                result = str(raw_result).strip().lower()

            # Now, apply the logic for counting based on the standardized 'result'
            if result in ["pass", "yes", "okay"]:
                passed_count += 1
            elif result in ["fail", "no", "not okay"]:
                failed_count += 1
                # Add failed item with status 'failed' to the new list
                items_requiring_attention.append({"name": item.ChecklistName, "type": item.ChecklistType, "status": "failed"})
                # You can remove failed_items_list.append if it's no longer used elsewhere in summary_percentages
                # failed_items_list.append({"name": item.ChecklistName, "type": item.ChecklistType}) 
            elif result == "no selection made":
                skipped_count += 1
                # Add skipped item with status 'skipped' to the new list
                items_requiring_attention.append({"name": item.ChecklistName, "type": item.ChecklistType, "status": "skipped"})
            else: # Catch-all for any other unexpected string values, treat as skipped
                skipped_count += 1
                items_requiring_attention.append({"name": item.ChecklistName, "type": item.ChecklistType, "status": "skipped"}) # Also add to attention list
            
    
    # Calculate percentages
    passed_percentage = (passed_count / total_items * 100) if total_items > 0 else 0
    failed_percentage = (failed_count / total_items * 100) if total_items > 0 else 0
    skipped_percentage = (skipped_count / total_items * 100) if total_items > 0 else 0

    summary = {
        "total_items": total_items,
        "passed_count": passed_count,
        "passed_percentage": passed_percentage,
        "failed_count": failed_count,
        "failed_percentage": failed_percentage,
        "skipped_count": skipped_count,
        "skipped_percentage": skipped_percentage,
        # "failed_items_list": failed_items_list, # Remove or keep if other parts use it
        "items_requiring_attention": items_requiring_attention # <-- ADD THIS NEW FIELD
    }

    return summary

def _calculate_group_pass_rates(checklist_data: FullChecklist, submitted_form_data: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Calculates the pass rate for each checklist group.
    """
    group_pass_rates = []

    for group in checklist_data.root:
        group_total_items = 0
        group_passed_count = 0
        
        for item in group.Checklist:
            group_total_items += 1
            unique_id = f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}"

            raw_result = submitted_form_data.get(unique_id)

            result = "no selection made" # Default assignment

            if raw_result is None:
                result = "no selection made"
            else:
                result = str(raw_result).strip().lower()

            if result in ["pass", "yes", "okay"]:
                group_passed_count += 1
        
        group_pass_percentage = 0.0
        if group_total_items > 0:
            group_pass_percentage = (group_passed_count / group_total_items) * 100
        
        group_pass_rates.append({
            "GroupName": group.GroupName,
            "PassRate": f"{group_pass_percentage:.0f}%" # Format as percentage string
        })
    
    return group_pass_rates

def _get_resolution_advice(item_name: str, item_type: str, item_status: str) -> str:
    """Provides resolution advice based on item type and its status (failed/skipped)."""
    item_type_lower = item_type.lower()
    
    if item_status == "failed":
        advice_map = {
            "pass/fail": f"For '{item_name}' (Failed): Inspect the component thoroughly for wear, damage, or malfunction. Consult a qualified mechanic for repair or replacement.",
            "yes/no": f"For '{item_name}' (Failed): Investigate why the condition is not met. Address the underlying issue (e.g., refill, repair, adjust) to ensure compliance.",
            "okay/not okay": f"For '{item_name}' (Failed): Identify the specific defect or anomaly. Immediate corrective action or professional repair is advised to restore the item to an 'Okay' state."
        }
        return advice_map.get(item_type_lower, f"For '{item_name}' (Failed): This item requires attention. Please consult the vehicle's maintenance manual or a professional for specific resolution steps.")
    
    elif item_status == "skipped":
        return f"For '{item_name}' (Skipped/No Selection): This item was not assessed during the inspection. It is highly recommended to perform a thorough check of this component to ensure it is in good working order and meets safety standards."
        
    else: # Fallback for unknown status
        return f"For '{item_name}' (Status Unknown): This item's status is unclear. A full assessment is recommended to determine necessary actions."

def _generate_comments_and_analysis(
    summary_percentages: Dict[str, Any],
    trip_advice_content: str # This is the overall advice from stream.py
) -> list: # Changed return type to list
    styles = getSampleStyleSheet()
    comments_lines = []

    # Customize paragraph styles for better PDF appearance
    h3_style = ParagraphStyle(
        'h3_custom',
        parent=styles['h3'],
        spaceBefore=10,
        spaceAfter=5,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    normal_style = ParagraphStyle(
        'normal_custom',
        parent=styles['Normal'],
        spaceBefore=5,
        spaceAfter=5,
        alignment=TA_LEFT,
        leading=14
    )
    
    # Add the general trip advice content from Streamlit
    if trip_advice_content:
        # Replace markdown headers with bold text and clean up newlines for PDF
        display_trip_advice = trip_advice_content.replace('## ⚠️ Trip Preparedness: Caution Needed', '<b>Overall Trip Preparedness: Caution Needed</b>')
        display_trip_advice = display_trip_advice.replace('## ✅ Trip Preparedness: All Clear!', '<b>Overall Trip Preparedness: All Clear!</b>')
        display_trip_advice = display_trip_advice.replace('\n', '<br/>') # Convert newlines to HTML breaks for Paragraph
        comments_lines.append(Paragraph(display_trip_advice, normal_style))
        comments_lines.append(Spacer(1, 0.1 * inch))


    # Start the detailed comments and analysis
    comments_lines.append(Paragraph("<b>Detailed Inspection Analysis:</b>", h3_style))
    comments_lines.append(Spacer(1, 0.1 * inch))

    total_items = summary_percentages.get("total_items", 0)
    passed_count = summary_percentages.get("passed_count", 0)
    failed_count = summary_percentages.get("failed_count", 0)
    skipped_count = summary_percentages.get("skipped_count", 0)
    passed_percentage = summary_percentages.get("passed_percentage", 0)
    # Ensure percentages are float for formatting
    passed_percentage = float(passed_percentage)
    failed_percentage = float(summary_percentages.get("failed_percentage", 0))
    skipped_percentage = float(summary_percentages.get("skipped_percentage", 0))
    
    items_requiring_attention = summary_percentages.get("items_requiring_attention", []) # <-- Ensure correct retrieval here

    # Overall Assessment based on percentages
    if passed_percentage >= 90:
        comments_lines.append(Paragraph(f"<b>Overall Assessment:</b> The vehicle recorded an excellent pass rate of {passed_percentage:.0f}% ({passed_count} out of {total_items} items passed). There were {failed_count} failed items ({failed_percentage:.0f}%) and {skipped_count} skipped items ({skipped_percentage:.0f}%). This indicates the vehicle is in <b>optimal condition</b> with minimal to no identified issues. Regular maintenance should continue to ensure its performance and ensure long-term reliability.", normal_style))
    elif passed_percentage >= 50:
        comments_lines.append(Paragraph(f"<b>Overall Assessment:</b> The vehicle recorded a pass rate of {passed_percentage:.0f}% ({passed_count} out of {total_items} items passed). There were {failed_count} failed items ({failed_percentage:.0f}%) and {skipped_count} skipped items ({skipped_percentage:.0f}%). This indicates a mixed condition with a notable number of areas requiring attention. Focused and timely corrective actions are essential to significantly improve the vehicle's reliability, safety, and compliance.", normal_style))
    elif skipped_count == total_items and total_items > 0:
        comments_lines.append(Paragraph(f"<b>Overall Assessment:</b> With all {total_items} items skipped, the inspection is incomplete. A pass rate of 0% was recorded as no items were positively assessed ({skipped_percentage:.0f}% skipped). A full and verified inspection is necessary to provide a definitive assessment of the vehicle's condition and compliance.", normal_style))
    else: # Low pass rate due to failures
        comments_lines.append(Paragraph(f"<b>Overall Assessment:</b> With a pass rate of {passed_percentage:.0f}% ({passed_count} out of {total_items} items passed), and {failed_count} failed items ({failed_percentage:.0f}%), this inspection highlights that the vehicle has <b>significant non-compliance issues</b>. Extensive repairs and maintenance are urgently required to meet operational and safety standards before the vehicle can be considered roadworthy.", normal_style))

    comments_lines.append(Spacer(1, 0.2 * inch))

     # Retrieve the new list of items requiring attention
    # items_requiring_attention = summary_percentages.get("items_requiring_attention", []) 

    # --- Advice for Items Requiring Attention ---
    if items_requiring_attention:
        comments_lines.append(Paragraph("<b>Resolution Advice for Items Requiring Attention:</b>", h3_style))
        comments_lines.append(Spacer(1, 0.1 * inch))
        for i, item_info in enumerate(items_requiring_attention):
            item_name = item_info.get("name", "Unknown Item")
            item_type = item_info.get("type", "Unknown Type")
            item_status = item_info.get("status", "unknown") # Retrieve the status (failed/skipped)
            
            # Pass the status to the advice function
            advice = _get_resolution_advice(item_name, item_type, item_status) 
            comments_lines.append(Paragraph(f"{i+1}. {advice}", normal_style))
            comments_lines.append(Spacer(1, 0.05 * inch))
    else:
        comments_lines.append(Paragraph("All inspected items passed or were fully assessed. No specific resolution advice needed.", normal_style))
        
    comments_lines.append(Spacer(1, 0.2 * inch))

    # Add general notes/disclaimer if any
    comments_lines.append(Paragraph("<b>General Notes & Disclaimer:</b>", h3_style))
    comments_lines.append(Spacer(1, 0.1 * inch))
    comments_lines.append(Paragraph("This report provides an assessment based on the submitted inspection data. It is recommended to consult with a certified mechanic for a professional diagnosis and repair of any identified issues. Regular maintenance is key to vehicle safety and longevity.", normal_style))

    return comments_lines