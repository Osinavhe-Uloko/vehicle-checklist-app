import datetime
import shutil
import streamlit as st
import json
from openai import OpenAI
from pydantic import BaseModel, Field, RootModel, AliasChoices
from typing import List, Literal, Optional
import os
import uuid
import random
import re
import tempfile

# Import the PDF generation function from the separate service file
from pdf_service import generate_inspection_pdf



if 'generate_form_clicked' not in st.session_state:
    st.session_state.generate_form_clicked = False
if 'checklist_data' not in st.session_state:
    st.session_state.checklist_data = None
if 'form_reset_trigger' not in st.session_state:
    st.session_state.form_reset_trigger = 0
if 'selectbox_indices' not in st.session_state:
    st.session_state.selectbox_indices = {}
if 'inspection_form_submitted' not in st.session_state:
    st.session_state.inspection_form_submitted = False
if 'submitted_form_data' not in st.session_state:
    st.session_state.submitted_form_data = None
if 'begin_inspection_clicked' not in st.session_state:
    st.session_state.begin_inspection_clicked = False

# Session states for the pre-inspection form
if 'pre_inspection_form_submitted' not in st.session_state:
    st.session_state.pre_inspection_form_submitted = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'vehicle_plate_number' not in st.session_state:
    st.session_state.vehicle_plate_number = None

#  Session state for storing the path to the generated PDF
if 'generated_pdf_path' not in st.session_state:
    st.session_state.generated_pdf_path = None
if 'generated_pdf_temp_dir' not in st.session_state:
    st.session_state.generated_pdf_temp_dir = None


# --- Custom CSS to fix selectbox cursor behavior ---
st.markdown("""
<style>
    /* Prevent text cursor on the main selectbox display area */
    /* Target the input element used by st.selectbox for displaying the selected value */
    [data-testid="stSelectbox"] input[type="text"] {
        cursor: default !important; /* Forces default arrow cursor */
    }

    /* Change cursor to pointer when hovering over the overall selectbox area */
    [data-testid="stSelectbox"] {
        cursor: pointer !important;
    }

    /* Target the clickable display area within the selectbox */
    [data-testid="stSelectbox"] > div[data-testid="stSelectboxProcessedOptions"] {
        cursor: pointer !important;
    }

    /* Also target the dropdown arrow icon itself for consistency */
    [data-testid="stSelectbox"] .st-bs { /* This class may vary slightly with Streamlit versions */
        cursor: pointer !important;
    }

    /* Target the first option in the dropdown list for "not-allowed" cursor */
    [data-testid="stVirtualDropdown"] [role="option"]:first-child {
        cursor: not-allowed !important;
        /* Optional: Add visual cues for unselectable */
        /* background-color: #333 !important; */
        /* color: #888 !important; */
    }
</style>
""", unsafe_allow_html=True)


# --- Pydantic Models for Checklist ---
class ChecklistItem(BaseModel):
    ChecklistName: str = Field(...)
    ChecklistSerialNo: int = Field(...)
    ChecklistId: str = Field(...)
    ChecklistType: Literal["Pass/Fail", "Yes/No", "Okay/Not Okay"] = Field(...)

class ChecklistGroup(BaseModel):
    GroupName: str = Field(...)
    GroupId: str = Field(...)
    SerialNo: int = Field(...)
    Checklist: List[ChecklistItem] = Field(...)

class FullChecklist(RootModel[List[ChecklistGroup]]):
    pass

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["openai_api_key"])

CONFIG_FILE = "config.json"

# --- Functions to manage OpenAI resources ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

@st.cache_resource
def setup_openai_resources(file_path="research.pdf"):
    """
    Sets up OpenAI file and vector store, caching the IDs.
    """
    config = load_config()
    file_id = config.get('file_id')
    vector_store_id = config.get('vector_store_id')

    if file_id and vector_store_id:
        print(f"Using existing file ID: {file_id} and vector store ID: {vector_store_id}")
        return file_id, vector_store_id

    try:
        if not file_id:
            print("Uploading file...")
            file_upload = client.files.create(file=open(file_path, "rb"), purpose='assistants')
            file_id = file_upload.id
            print(f"File uploaded successfully with ID: {file_id}")

        if not vector_store_id:
            print("Creating vector store...")
            vector_store = client.vector_stores.create(name="Research Checklist Store")
            vector_store_id = vector_store.id
            print(f"Vector store created with ID: {vector_store_id}")

            print(f"Adding file {file_id} to vector store {vector_store_id}...")
            file_batch = client.vector_stores.files.create_and_poll(
                vector_store_id=vector_store_id,
                file_id=file_id
            )

            if file_batch.status == "failed":
                st.error("Error: File processing failed. Please check OpenAI dashboard for details.")
                return None, None
            else:
                print(f"File status in vector store: {file_batch.status}")

        if file_id and vector_store_id:
            save_config({'file_id': file_id, 'vector_store_id': vector_store_id})
            print("File and Vector Store IDs saved to config.json for future use.")
            return file_id, vector_store_id

    except FileNotFoundError:
        st.error(f"Error: The file '{file_path}' was not found. Ensure it's in your repository.")
    except Exception as e:
        st.error(f"An unexpected error occurred during file/vector store setup: {e}")
    return None, None

# --- Function to get checklist from OpenAI ---
def get_checklist_from_openai(user_trip_details, vector_store_id):
    if not vector_store_id:
        st.error("Vector store not set up. Cannot generate checklist.")
        return None

    system_prompt = """
    You are an expert assistant for **vehicle maintenance and trip preparation**, and your sole purpose is to generate comprehensive and strictly structured vehicle checklists.
    Your primary task is to analyze provided documents and user requests to generate these checklists.

    **Instructions for Interpretation and JSON Schema Adherence:**
    1.  **Interpret Vehicle Relevance:** Carefully interpret user requests. If the request can be reasonably connected to vehicle inspection, maintenance, or trip preparation, even if not explicitly stated, proceed with generating a checklist. Your goal is to infer vehicle-related intent.
    2.  **Default Checklist for Ambiguity:** If the direct vehicle context is minimal but the request implies a journey or general preparedness (e.g., "going to Abuja"), infer a general vehicle travel scenario (e.g., car road trip) and generate a standard comprehensive checklist. Do NOT refuse to generate JSON if a vehicle context can be inferred.
    3.  **Adherence to FullChecklist Schema:** Your output MUST always be a valid JSON object conforming STRICTLY to the `FullChecklist` Pydantic schema. You MUST include ALL required fields for `ChecklistGroup` and `ChecklistItem`.
        * For each `ChecklistGroup`, you MUST include: `GroupName` (string), `GroupId` (unique string, e.g., UUID or "group-1"), `SerialNo` (integer), and `Checklist` (a list of ChecklistItem objects).
        * For each `ChecklistItem`, you MUST include: `ChecklistName` (question string), `ChecklistSerialNo` (integer), `ChecklistId` (unique string, e.g., UUID or "item-1"), and `ChecklistType` (strictly one of 'Pass/Fail', 'Yes/No', or 'Okay/Not Okay').
    4.  **Question Formatting:** 'ChecklistName' MUST be phrased as a clear, concise question.
    5.  **Unique IDs:** 'GroupId' and 'ChecklistId' MUST always be unique string identifiers.
    6.  **No Extraneous Text:** Respond ONLY with the JSON object. Do NOT include any introductory or concluding text, explanations, conversational remarks, or any text outside the JSON structure.
    7.  **Out-of-Scope Requests (Rare):** If a user's request is **unequivocally** and **completely unrelated** to any vehicle context (e.g., "Tell me a joke," "Write a poem about flowers", "How to prepare fried rice"), you MUST NOT generate a checklist with items. Instead, you MUST return an **empty JSON array `[]`** conforming to the `FullChecklist` schema. Do NOT return plain text in this case. Strive to find a vehicle-related interpretation first.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [{"type": "text", "text": user_trip_details}]},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "FullChecklist",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "checklist": {
                                "type": "array",
                                "items": FullChecklist.model_json_schema().get("items")
                            }
                        }
                    }
                }
            }
        )

        checklist_json_string = response.choices[0].message.content
        parsed_checklist = None

        if not checklist_json_string or checklist_json_string.strip().lower() == "null":
            print("Model returned an empty or null response, validating as empty list.")
            parsed_checklist = FullChecklist.model_validate([]) # Treat null as empty list
        else:
            try:
                raw_data = json.loads(checklist_json_string)
                if isinstance(raw_data, dict) and "checklist" in raw_data:
                    potential_list = raw_data["checklist"]
                else:
                    potential_list = raw_data

                if not isinstance(potential_list, list):
                    st.warning("Model did not return a list at the top level for the checklist data. Initializing with empty checklist.")
                    potential_list = []

                parsed_checklist = FullChecklist.model_validate(potential_list)
                print("Successfully parsed the structured output.")

            except json.JSONDecodeError as e:
                st.error(f"Error parsing JSON from OpenAI: {e}. Raw response: {checklist_json_string}")
                return None
            except Exception as e:
                st.error(f"Error validating checklist against schema: {e}. Raw response: {checklist_json_string}")
                return None
        return parsed_checklist

    except Exception as e:
        st.error(f"Error generating checklist: {e}")
        return None

# --- Generate Trip Advice based on submitted form data ---
def generate_trip_advice(submitted_data: dict, checklist_structure: FullChecklist) -> str:
    """
    Analyzes submitted inspection data against the checklist structure
    to provide advice on trip preparedness.
    """
    issues_found = []
    
 
    checklist_items_map = {}
    for group in checklist_structure.root:
        for item in group.Checklist:
            checklist_items_map[item.ChecklistId] = {"name": item.ChecklistName, "type": item.ChecklistType}


    for item_id, response in submitted_data.items():
        item_details = checklist_items_map.get(item_id, {"name": "Unknown Item", "type": ""})
        item_name = item_details["name"]
        item_type = item_details["type"]

        # Identify negative responses based on ChecklistType
        if item_type == "Pass/Fail" and response == "Fail":
            issues_found.append(f"- {item_name}: Failed")
        elif item_type == "Yes/No" and response == "No":
            issues_found.append(f"- {item_name}: No")
        elif item_type == "Okay/Not Okay" and response == "Not Okay":
            issues_found.append(f"- {item_name}: Not Okay")
        elif response is None: # Handle cases where an item might not have been selected
            issues_found.append(f"- {item_name}: No selection made (please check)")

    if issues_found:
        advice = "## ⚠️ Trip Preparedness: Caution Needed\n\n"
        advice += "Based on your inspection, there are items that require attention before your trip:\n"
        advice += "\n".join(issues_found)
        advice += "\n\nIt is highly recommended to address these issues to ensure a safe journey."
        return advice
    else:
        return "## ✅ Trip Preparedness: All Clear!\n\nYour vehicle inspection indicates that you are well-prepared for your trip. Have a safe journey!"

# def generate_inspection_summary_and_advice(submitted_data: dict, checklist_structure: FullChecklist, vehicle_plate_number: str) -> str:
#     """
#     Generates a concise summary and advice for the inspection report,
#     mimicking the "Comments & Analysis" section from the reference PDF.
#     """
#     total_items = 0
#     passed_items = 0
#     failed_items = 0
#     failed_list = []
#     recommendations = []
    
#     checklist_items_map = {}
#     for group in checklist_structure.root:
#         for item in group.Checklist:
#             checklist_items_map[item.ChecklistId] = {"name": item.ChecklistName, "type": item.ChecklistType}
#             total_items += 1

#     for item_id, response in submitted_data.items():
#         item_details = checklist_items_map.get(item_id)
#         if not item_details:
#             continue
            
#         item_name = item_details["name"]
#         item_type = item_details["type"]

#         is_failed = False
#         if item_type == "Pass/Fail" and response == "Fail":
#             is_failed = True
#         elif item_type == "Yes/No" and response == "No":
#             is_failed = True
#         elif item_type == "Okay/Not Okay" and response == "Not Okay":
#             is_failed = True
#         elif response is None or response == "No selection made": 
#             is_failed = True
        
#         if is_failed:
#             failed_items += 1
#             failed_list.append(item_name)
#         else:
#             passed_items += 1
            
#     # Calculate pass rate
#     pass_rate = (passed_items / total_items * 100) if total_items > 0 else 0

#     # --- Constructing the Summary ---
#     summary_parts = []
#     report_date = datetime.datetime.now().strftime("%B %d, %Y")

#     # Opening statement
#     if failed_items > 0:
#         summary_parts.append(f"The vehicle inspection conducted on {report_date}, for Vehicle ID {vehicle_plate_number} revealed several critical findings that require immediate attention.")
#     else:
#         summary_parts.append(f"The vehicle inspection conducted on {report_date}, for Vehicle ID {vehicle_plate_number} revealed satisfactory findings, indicating good vehicle condition.")

#     # Failed items list
#     if failed_list:
#         summary_parts.append("\n- The vehicle failed to meet standards in multiple areas, including:")
#         for item in failed_list:
#             summary_parts.append(f"  - {item}")
#         summary_parts.append("\nThese failures have significant implications for the vehicle's compliance with regulations and safety standards, which could affect its operational status and legality on the road.")

#     # Recommendations
#     summary_parts.append("\nNext actions are recommended as follows:")
#     if "Air Conditioning System" in [g.GroupName for g in checklist_structure.root] and any(item in failed_list for item in ["Is the air conditioning blowing cold air efficiently?", "Are the AC controls functioning correctly?", "Is the air filter clean?"]):
#         recommendations.append("Address issues related to the Air Conditioning System to ensure comfortable and healthy cabin environment.")
#     if "Emergency Kit" in [g.GroupName for g in checklist_structure.root] and any(item in failed_list for item in ["Is the first aid kit fully stocked?", "Are there fresh water bottles in the kit?", "Is there a flashlight with working batteries?", "Are the emergency contact numbers updated?", "Is there a safety triangle or emergency flare available?"]):
#         recommendations.append("Ensure the Emergency Kit is complete and up-to-date for roadside emergencies.")
#     if "Spare Tire and Tools" in [g.GroupName for g in checklist_structure.root] and any(item in failed_list for item in ["Is the spare tire properly inflated?", "Are all necessary tools (jack, wrench) available?", "Is the spare tire free from visible damage?"]):
#         recommendations.append("Verify the spare tire and tools are in good working order for unexpected tire issues.")
    
#     # Generic recommendation if no specific ones apply or as a fallback
#     if not recommendations:
#         if failed_items > 0:
#             recommendations.append("Review all identified failures and take appropriate corrective actions to improve vehicle safety and compliance.")
#         else:
#             recommendations.append("Continue regular maintenance and inspections to ensure the vehicle remains in optimal condition.")

#     for rec in recommendations:
#         summary_parts.append(f"- {rec}")

#     # Overall Pass Rate
#     if total_items > 0:
#         summary_parts.append(f"\nOverall, the vehicle passed {passed_items} out of {total_items} items, resulting in a pass rate of {pass_rate:.0f}%.")
#         if pass_rate < 50:
#             summary_parts.append("This indicates a need for considerable improvement to meet operational standards effectively. Timely corrective measures will enhance the vehicle's reliability and safety for operations.")
#         else:
#             summary_parts.append("This indicates good progress towards meeting operational standards. Continued diligent maintenance will ensure reliability and safety for operations.")

#     return "\n".join(summary_parts)

# --- Streamlit App Layout ---
st.set_page_config(layout="wide", page_icon="🚗", page_title="Vehicle Trip Checklist Generator")

# --- Random Placeholder Texts ---
VEHICLE_PROMPTS = [
    "A long road trip from Lagos to Abuja in a sedan, focusing on tire pressure, oil levels, and brake fluid.",
    "Pre-winter maintenance check for an SUV, including antifreeze, battery, and wiper blades.",
    "Daily commute vehicle inspection for a small car, particularly checking tire tread, lights, and horn.",
    "Preparing a pickup truck for a heavy load haul, focusing on suspension, tire condition, and engine performance.",
    "Getting a family minivan ready for a summer vacation drive, checking AC, emergency kit, and spare tire.",
    "Routine check-up for a commercial van before deliveries, inspecting mirrors, exhaust, and fuel system.",
    "Off-road adventure preparation for a 4x4, checking differentials, winches, and recovery gear.",
    "Motorcycle pre-ride safety check: chain tension, brake lines, and helmet condition.",
    "Boat trailer inspection before launching: lights, bearings, and hitch security.",
    "General vehicle health check for an older car, looking at rust, leaks, and dashboard warning lights."
]


file_id, vector_store_id = setup_openai_resources()


st.title("🚗 Vehicle Trip Checklist Generator")

# 7) The Vehicle Inspection App and Start New Inspection button (always visible after submission)
# This section now comes first in the conditional logic because it's the "end state"
# and offers the option to restart the entire process.
if st.session_state.inspection_form_submitted:
    st.success("Inspection form submitted successfully!")
    st.markdown("---")

    # 6) The trip awareness section
    if st.session_state.submitted_form_data and st.session_state.checklist_data:
        trip_advice = generate_trip_advice(st.session_state.submitted_form_data, st.session_state.checklist_data)
        st.markdown(trip_advice) # Display on screen
    else:
        st.warning("Could not generate trip advice due to missing form data or checklist.")

    st.markdown("---")
    
    # NEW: Download PDF button
    # The button will only appear if generated_pdf_path exists and the file is there.
    # The file will persist until 'Start New Inspection' is clicked.
    if st.session_state.generated_pdf_path and os.path.exists(st.session_state.generated_pdf_path):
        try:
            with open(st.session_state.generated_pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="Download Inspection Report PDF",
                    data=pdf_file.read(),
                    file_name="Inspection Report.pdf", # Corrected file name shown to user
                    mime="application/pdf"
                )
        except Exception as e:
            st.error(f"Error preparing PDF for download: {e}")
    # st.markdown("---")
    st.link_button(
        label="TRY VEHICLE INSPECTION APP",
        url="https://www.google.com"
    )

    if st.button("Start New Inspection", key=f"new_inspection_btn_{st.session_state.form_reset_trigger}"):
        # Clean up the temporary PDF file when starting a new inspection
        if st.session_state.generated_pdf_path and os.path.exists(st.session_state.generated_pdf_path):
            try:
                # Remove the PDF file
                os.remove(st.session_state.generated_pdf_path)
            except OSError as e:
                st.warning(f"Could not remove old PDF file: {e}")
            
            # Remove the temporary directory if it exists and we stored its path
            if st.session_state.generated_pdf_temp_dir and os.path.exists(st.session_state.generated_pdf_temp_dir):
                try:
                    shutil.rmtree(st.session_state.generated_pdf_temp_dir)
                except OSError as e:
                    st.warning(f"Could not remove temporary PDF directory: {e}")

            st.session_state.generated_pdf_path = None # Clear the path from session state
            st.session_state.generated_pdf_temp_dir = None # Clear the temp directory path

        st.session_state.generate_form_clicked = False
        st.session_state.checklist_data = None
        st.session_state.selectbox_indices = {}
        st.session_state.form_reset_trigger += 1
        st.session_state.inspection_form_submitted = False
        st.session_state.submitted_form_data = None
        st.session_state.begin_inspection_clicked = False
        st.session_state.pre_inspection_form_submitted = False # Reset pre-inspection form state
        st.session_state.user_email = None # Reset user email
        st.session_state.user_name = None # Reset user name
        st.session_state.vehicle_plate_number = None # Reset plate number
        st.rerun()

# 4) The form generation section (and 5) form submission is nested within it)
elif st.session_state.checklist_data and st.session_state.generate_form_clicked and st.session_state.begin_inspection_clicked and not st.session_state.inspection_form_submitted:
    # Check if the generated checklist is empty, implying an out-of-scope request
    if not st.session_state.checklist_data.root:
        st.error("Your request was not related to vehicle inspection or trip preparation. Please enter a vehicle-related query.")
        # Reset state to allow new input
        st.session_state.generate_form_clicked = False
        st.session_state.checklist_data = None
        st.session_state.selectbox_indices = {}
        st.session_state.form_reset_trigger += 1
        st.session_state.begin_inspection_clicked = False
        st.session_state.pre_inspection_form_submitted = False
        st.session_state.user_email = None
        st.session_state.user_name = None # Reset user name
        st.session_state.vehicle_plate_number = None
        st.session_state.generated_pdf_path = None # NEW: Reset PDF path
        st.session_state.generated_pdf_temp_dir = None # NEW: Reset temp dir path
        st.rerun()
    else:
        st.subheader("Vehicle Inspection Form")
        st.write("Please fill out the form based on your vehicle's condition.")

        with st.form(key=f"inspection_form_{st.session_state.form_reset_trigger}"):
            form_data = {}

            for group in st.session_state.checklist_data.root:
                st.markdown(f"**{group.GroupName}**")
                for item in group.Checklist:
                    selectbox_key = f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}"

                    options_map = {
                        "Pass/Fail": ["Pass", "Fail"],
                        "Yes/No": ["Yes", "No"],
                        "Okay/Not Okay": ["Okay", "Not Okay"]
                    }
                    actual_options = options_map.get(item.ChecklistType, [])
                    display_options = ["--- Select ---"] + actual_options

                    stored_index = st.session_state.selectbox_indices.get(selectbox_key, 0)

                    if 0 <= stored_index < len(display_options):
                        current_index = stored_index
                    else:
                        current_index = 0

                    selected_option = st.selectbox(
                        item.ChecklistName,
                        display_options,
                        index=current_index,
                        key=selectbox_key
                    )

                    try:
                        st.session_state.selectbox_indices[selectbox_key] = display_options.index(selected_option)
                    except ValueError:
                        st.session_state.selectbox_indices[selectbox_key] = 0

                    if selected_option != "--- Select ---":
                        form_data[item.ChecklistId] = selected_option
                    else:
                        form_data[item.ChecklistId] = None

            # 5) The form submission section
            submitted = st.form_submit_button("Submit Inspection Form")

            if submitted:
                with st.spinner("Submitting inspection results and generating report..."):
                    st.session_state.selectbox_indices = {}
                    st.session_state.form_reset_trigger += 1
                    st.session_state.inspection_form_submitted = True
                    st.session_state.submitted_form_data = form_data
                    st.session_state.begin_inspection_clicked = False

                    # Generate trip advice (needed for PDF content)
                    trip_advice_content = generate_trip_advice(
                        st.session_state.submitted_form_data,
                        st.session_state.checklist_data
                    )

                    # if st.session_state.inspection_form_submitted and st.session_state.submitted_form_data:
                    #     comments_analysis_text = generate_inspection_summary_and_advice(
                    #         st.session_state.submitted_form_data,
                    #         st.session_state.checklist_data,
                    #         st.session_state.vehicle_plate_number
                    #     )

                    # Generate PDF report in a temporary file
                    # We create a temporary directory to store our named PDF file
                    pdf_temp_dir = os.path.join(tempfile.gettempdir(), f"streamlit_pdf_report_{uuid.uuid4()}")
                    os.makedirs(pdf_temp_dir, exist_ok=True)
                    st.session_state.generated_pdf_temp_dir = pdf_temp_dir # Store temp dir for cleanup


                    pdf_file_path = None
                    try:
                        pdf_file_path = generate_inspection_pdf(
                            st.session_state.user_name,
                            st.session_state.user_email,
                            st.session_state.vehicle_plate_number,
                            st.session_state.checklist_data,
                            st.session_state.submitted_form_data,
                            trip_advice_content,
                            file_name="Inspection Report.pdf"# Pass the desired path
                        )
                        if pdf_file_path:
                            st.session_state.generated_pdf_path = pdf_file_path # Store path for download button
                            st.success("Inspection results submitted and report generated. You can now download the PDF.")
                        else:
                            st.error("Failed to generate PDF report.")
                    except Exception as e:
                        st.error(f"An unexpected error occurred during PDF generation: {e}")
                        # Ensure cleanup of the temp directory if generation failed
                        if st.session_state.generated_pdf_temp_dir and os.path.exists(st.session_state.generated_pdf_temp_dir):
                            shutil.rmtree(st.session_state.generated_pdf_temp_dir)
                        st.session_state.generated_pdf_path = None # Clear path in session state
                        st.session_state.generated_pdf_temp_dir = None
                st.rerun()

# 3) The Begin inspection section and Pre-inspection form
elif st.session_state.checklist_data and st.session_state.generate_form_clicked and not st.session_state.begin_inspection_clicked:
    # Check if the generated checklist is empty, implying an out-of-scope request
    if not st.session_state.checklist_data.root:
        st.error("Your request was not related to vehicle inspection or trip preparation. Please enter a vehicle-related query.")
        # Reset state to allow new input
        st.session_state.generate_form_clicked = False
        st.session_state.checklist_data = None
        st.session_state.selectbox_indices = {}
        st.session_state.form_reset_trigger += 1
        st.session_state.begin_inspection_clicked = False
        st.session_state.pre_inspection_form_submitted = False
        st.session_state.user_email = None
        st.session_state.user_name = None # Reset user name
        st.session_state.vehicle_plate_number = None
        st.session_state.generated_pdf_path = None # NEW: Reset PDF path
        st.session_state.generated_pdf_temp_dir = None # NEW: Reset temp dir path
        st.rerun()
    else:
        st.markdown("---")
        st.success("Checklist generated successfully!")

        # Display the generated checklist
        st.markdown("## Generated Checklist Preview")
        for group in st.session_state.checklist_data.root:
            st.markdown(f"### {group.GroupName}")
            for item in group.Checklist:
                st.markdown(
                    f"- {item.ChecklistSerialNo}. {item.ChecklistName} (Type: <span style='color:green; font-weight:bold;'>{item.ChecklistType}</span>)",
                    unsafe_allow_html=True
                )
        st.markdown("---")

        # Pre-inspection form for email and plate number
        if not st.session_state.pre_inspection_form_submitted:
            st.subheader("Enter Your Details to Begin Inspection")
            with st.form(key=f"pre_inspection_details_form_{st.session_state.form_reset_trigger}"):
                user_name_input = st.text_input("Full Name", value=st.session_state.user_name or "", help="Enter your full name.", placeholder="John Doe")
                user_email_input = st.text_input("Email", value=st.session_state.user_email or "", help="Enter your email address.", placeholder="name@example.com")
                vehicle_plate_input = st.text_input("Vehicle Plate Number", value=st.session_state.vehicle_plate_number or "", placeholder="e.g., ABC-123AA", help="Format: AAA-123AA (3 letters, hyphen, 3 digits, 2 letters)")
                
                pre_form_submitted = st.form_submit_button("Submit Details")

                if pre_form_submitted:
                    if not user_name_input.strip(): # Check for empty or just whitespace
                        st.error("Please enter your full name.")
                        pre_form_submitted = False
                    elif not all(char.isalpha() or char.isspace() or char == '-' for char in user_name_input):
                        st.error("Please enter a valid name (letters, spaces, and hyphens only).")
                        pre_form_submitted = False
                    elif len(user_name_input.strip()) < 2: # Optional: minimum length check
                        st.error("Name must be at least 2 characters long.")
                        pre_form_submitted = False
                    elif not user_email_input.strip():
                        st.error("Please enter your full name.")
                        pre_form_submitted = False # Check for empty or just whitespace
                    # Validate Email
                    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", user_email_input):
                        st.error("Please enter a valid email address.")
                        pre_form_submitted = False # Prevent submission if validation fails
                    
                    # Validate Vehicle Plate Number (e.g., ABC-123DE)
                    # elif pre_form_submitted and not vehicle_plate_input.strip():
                    #     st.error("Please enter the Vehicle Plate Number.")
                    #     pre_form_submitted = False
                    elif pre_form_submitted and not re.match(r"^[A-Z]{3}-\d{3}[A-Z]{2}$", vehicle_plate_input.upper()):
                        st.error("Please enter a valid Vehicle Plate Number in the format AAA-123AA.")
                        pre_form_submitted = False
                    
                    if pre_form_submitted: # Only proceed if all validations passed
                        st.session_state.user_name = user_name_input
                        st.session_state.user_email = user_email_input
                        st.session_state.vehicle_plate_number = vehicle_plate_input.upper() # Store uppercase
                        st.session_state.pre_inspection_form_submitted = True
                        st.rerun() # Rerun to hide this form and show BEGIN INSPECTION button
        else:
            # Only show BEGIN INSPECTION button if pre-inspection form is submitted
            st.success(f"Details submitted! A copy of the report will be made available for you to download after the inspection")
            st.markdown("---")
            if st.button("BEGIN INSPECTION", key=f"begin_inspection_btn_{st.session_state.form_reset_trigger}"):
                st.session_state.begin_inspection_clicked = True
                st.rerun()

# 1) The Input section
# 2) The generate checklist section (nested within input)
else:
    st.write("Enter your trip details and I'll generate a comprehensive vehicle checklist for you!")
    st.subheader("Your Trip Request")

    random_placeholder = random.choice(VEHICLE_PROMPTS)

    user_trip_details = st.text_area(
        "Describe your trip",
        placeholder=random_placeholder,
        key=f"trip_details_input_{st.session_state.form_reset_trigger}"
    )

    # Determine the actual input to use for checklist generation
    # If the user has typed something, use that. Otherwise, use the placeholder as default.
    actual_input = user_trip_details if user_trip_details else random_placeholder

    if st.button("Generate Checklist", key=f"generate_button_{st.session_state.form_reset_trigger}"):
        if actual_input:
            with st.spinner("Generating your comprehensive checklist..."):
                st.session_state.checklist_data = get_checklist_from_openai(actual_input, vector_store_id)
                
                if st.session_state.checklist_data is not None:
                    # Check if the generated checklist is empty (implies out-of-scope based on system_prompt)
                    if not st.session_state.checklist_data.root:
                        st.error("Your request was not related to vehicle inspection or trip preparation. Please enter a vehicle-related query.")
                        # Reset to allow new input
                        st.session_state.generate_form_clicked = False
                        st.session_state.checklist_data = None
                        st.session_state.selectbox_indices = {}
                        st.session_state.begin_inspection_clicked = False
                        st.session_state.pre_inspection_form_submitted = False
                        st.session_state.user_email = None
                        st.session_state.user_name = None
                        st.session_state.generated_pdf_path = None
                        st.session_state.generated_pdf_temp_dir = None
                    else:
                        st.session_state.generate_form_clicked = True
                        st.session_state.inspection_form_submitted = False
                        st.session_state.begin_inspection_clicked = False
                        st.session_state.pre_inspection_form_submitted = False # Ensure this is reset for new generation
                        st.session_state.user_name = None
                        st.session_state.generated_pdf_path = None
                        st.session_state.generated_pdf_temp_dir = None
                        
                        # Initialize selectbox_indices
                        st.session_state.selectbox_indices = {
                            f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}": 0
                            for group in st.session_state.checklist_data.root
                            for item in group.Checklist
                        }
                st.session_state.form_reset_trigger += 1
                st.rerun()
        else:
            st.warning("Please describe your trip to generate a checklist.")