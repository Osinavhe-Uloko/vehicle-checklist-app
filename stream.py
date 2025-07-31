import datetime
import shutil
import streamlit as st
import json
from openai import OpenAI
from pydantic import BaseModel, Field, RootModel, AliasChoices
from typing import List, Literal, Optional, Dict, Any
import os
import uuid
import random
import re
import tempfile
import segment.analytics as analytics # For server-side tracking
import time # Import the time module

# Import for Pydantic validation errors
from pydantic.v1.error_wrappers import ValidationError # Import specific to Pydantic v1, as indicated by your error

# Import the PDF generation function from the separate service file
from pdf_service import generate_inspection_pdf
import pdf_service # To access _calculate_summary_percentages

# --- Utility functions for config management ---
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
# --- End Utility functions ---

# --- Global System Prompts for Assistants ---
SYSTEM_PROMPT_CHECKLIST = """
You are an expert assistant for **vehicle maintenance and trip preparation**, and your sole purpose is to generate comprehensive and strictly structured vehicle checklists.
Your primary task is to analyze provided documents and user requests to generate these checklists.

**Instructions for Interpretation and JSON Schema Adherence:**
1.  **Interpret Vehicle Relevance:** Carefully interpret user requests. If the request can be reasonably connected to vehicle inspection, maintenance, or trip preparation, even if not explicitly stated, proceed with generating a checklist. Your goal is to infer vehicle-related intent.
2.  **Default Checklist for Ambiguity:** If the direct vehicle context is minimal but the request implies a journey or general preparedness (e.g., "going to Abuja"), infer a general vehicle travel scenario (e.g., car road trip) and generate a standard comprehensive checklist. Do NOT refuse to generate JSON if a vehicle context can be inferred.
3.  **Adherence to FullChecklist Schema:** Your output MUST always be a valid JSON **array** conforming STRICTLY to the `FullChecklist` Pydantic schema. This means the top-level structure of your JSON response MUST be an array `[...]` containing `ChecklistGroup` objects. You MUST include ALL required fields for `ChecklistGroup` and `ChecklistItem`.
    * For each `ChecklistGroup`, you MUST include: `GroupName` (string), `GroupId` (unique string, e.g., UUID or "group-1"), `SerialNo` (integer), and `Checklist` (a list of ChecklistItem objects).
    * For each `ChecklistItem`, you MUST include: `ChecklistName` (question string), `ChecklistSerialNo` (integer), `ChecklistId` (unique string, e.g., UUID or "item-1"), and `ChecklistType` (strictly one of 'Pass/Fail', 'Yes/No', or 'Okay/Not Okay').
4.  **Question Formatting:** 'ChecklistName' MUST be phrased as a clear, concise question.
5.  **Unique IDs:** 'GroupId' and 'ChecklistId' MUST always be unique string identifiers.
6.  **No Extraneous Text:** Respond ONLY with the JSON object. Do NOT include any introductory or concluding text, explanations, conversational remarks, or any text outside the JSON structure.
7.  **Out-of-Scope Requests (Rare):** If a user's request is **unequivocally** and **completely unrelated** to any vehicle context (e.g., "Tell me a joke," "Write a poem about flowers", "How to prepare fried rice"), you MUST NOT generate a checklist with items. Instead, you MUST return an **empty JSON array `[]`** conforming to the `FullChecklist` schema. Do NOT return plain text in this case. Strive to find a vehicle-related interpretation first.
"""

SYSTEM_PROMPT_ADVICE = """
You are an expert assistant for **vehicle maintenance and trip preparation**, specializing in providing comprehensive and actionable advice based on vehicle inspection results.
Your primary task is to analyze the provided inspection data and offer tailored recommendations.

**Instructions:**
1.  **Analyze Inspection Data:** Carefully review the `submitted_form_data` which contains the results of the vehicle inspection. Pay close attention to items marked 'Failed', 'Skipped', or 'N/A (Not Applicable)'.
2.  **Generate Actionable Advice:**
    * For each 'Failed' item, provide clear, concise, and actionable advice or recommendations for repair, immediate attention, or professional inspection.
    * For each 'Skipped' item, emphasize the importance of checking them and suggest how to properly inspect them or why they should not be skipped.
    * **For each 'N/A (Not Applicable)' item, explain why it might be considered not applicable in certain contexts, or suggest what similar or alternative checks might be relevant if the item's function is crucial for other vehicle types or situations.**
3.  **Categorize Advice:** Group advice logically (e.g., by system like "Engine & Fluids", "Tires & Brakes", "General Checks & Considerations for N/A Items").
4.  **Overall Summary:** Provide an overall summary of the vehicle's condition based on the inspection. State clearly if the vehicle appears ready for the trip or if significant attention is required.
5.  **Safety Emphasis:** Emphasize safety and the importance of professional help for critical issues.
6.  **No Extraneous Text:** Respond ONLY with the advice and summary. Do NOT include conversational remarks, introductory phrases like "Based on your inspection...", or any text outside the core advice.
7.  **"All Clear" Scenario:** If all items are "Passed", clearly state that the vehicle appears to be in good condition for the trip, but always recommend routine checks.
8.  **Contextualize Advice:** Relate advice back to the specific item and its implications for a trip. For example, for a failed tire, discuss the risks of blowouts or reduced handling.
"""
# --- End Global System Prompts ---


# --- Pydantic Models (as defined in your pdf_service.py) ---
# It's better to define these once or import them from a shared models file if used elsewhere.
# Assuming you want them in stream.py for direct use with the LLM output.
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
# --- End Pydantic Models ---


# --- Session State Initializations ---
# UI Control Flags
if 'show_generate_input' not in st.session_state:
    st.session_state.show_generate_input = True
if 'show_checklist_overview' not in st.session_state:
    st.session_state.show_checklist_overview = False
if 'show_inspection_form_actual' not in st.session_state:
    st.session_state.show_inspection_form_actual = False
if 'show_report_section' not in st.session_state:
    st.session_state.show_report_section = False



# Data and Other Operational States
if 'checklist_data' not in st.session_state:
    st.session_state.checklist_data = None
if 'form_reset_trigger' not in st.session_state:
    st.session_state.form_reset_trigger = 0
if 'selectbox_indices' not in st.session_state:
    st.session_state.selectbox_indices = {}
if 'submitted_form_data' not in st.session_state:
    st.session_state.submitted_form_data = None
if 'pre_inspection_form_submitted' not in st.session_state:
    st.session_state.pre_inspection_form_submitted = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'vehicle_plate_number' not in st.session_state:
    st.session_state.vehicle_plate_number = None
if 'generated_pdf_path' not in st.session_state:
    st.session_state.generated_pdf_path = None
if 'generated_pdf_temp_dir' not in st.session_state:
    st.session_state.generated_pdf_temp_dir = None
if 'last_user_input' not in st.session_state:
    st.session_state.last_user_input = ''
if 'trip_advice_content' not in st.session_state:
    st.session_state.trip_advice_content = None

# New: Initialize total_session_tokens
if 'total_session_tokens' not in st.session_state:
    st.session_state.total_session_tokens = 0
if 'start_inspection_time' not in st.session_state:
    st.session_state.start_inspection_time = None

# --- Analytics ID Generation ---
# Generate a unique User ID (anonymous_id for persistent tracking) if not already present
# This ID persists across sessions for the same browser/device
if 'user_anonymous_id' not in st.session_state:
    st.session_state.user_anonymous_id = str(uuid.uuid4())

# Generate a unique session ID if not already present
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    # Track "Application Viewed" only on the very first load of a session
    
    # --- Segment Python SDK Initialization (for server-side events) ---
    # This is for events triggered from your Python backend logic
    analytics.write_key = st.secrets["segment_write_key"] # Your Python/Backend Write Key
    analytics.debug = True # Set to False in production
    # --- End Segment Python SDK Initialization ---

    analytics.track(
        user_id=st.session_state.session_id, # Use the persistent anonymous ID as user_id
        event='Application Viewed',
        properties={
            'app_name': 'Vehicle Trip Checklist Generator',
            'page_name': 'Main Dashboard',
            'device_type': 'Web', # Streamlit runs in a browser
            # 'session_id': st.session_state.session_id, # Pass session_id as a property
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z' # ISO 8601 with Z for UTC
        }
    )

# --- Segment analytics.js (JavaScript SDK) Initialization (for browser-side events) ---
# This loads Segment's JavaScript library in the user's browser.
# It's safer to store this in Streamlit secrets too, e.g., st.secrets["segment_js_write_key"]
segment_js_write_key = st.secrets["segment_js_write_key"]

segment_js_snippet = f"""
<script type="text/javascript">
  !(function(){{var analytics=window.analytics=window.analytics||[];if(!analytics.initialize)if(analytics.invoked)window.console&&console.error&&console.error("Segment snippet included twice.");else{{analytics.invoked=!0;analytics.methods=["trackSubmit","trackClick","trackLink","trackForm","page","identify","reset","group","tracks","ready","alias","debug","pageview","load","ready","track","once","off","on"];analytics.factory=function(t){{return function(){{var e=Array.prototype.slice.call(arguments);e.unshift(t);analytics.push(e);return analytics}}}};for(var t=0;t<analytics.methods.length;t++){{var e=analytics.methods[t];analytics[e]=analytics.factory(e)}}analytics.load=function(t,n){{var r=document.createElement("script");r.type="text/javascript";r.async=!0;r.src="https://cdn.segment.com/analytics.js/v1/"+t+"/analytics.min.js";var a=document.getElementsByTagName("script")[0];a.parentNode.insertBefore(r,a)}};analytics.SNIPPET_VERSION="4.1.0";
  analytics.load("{segment_js_write_key}");
  analytics.page(); // This will automatically track a "Page Viewed" event on load
  }}());
</script>
"""

# Use st.components.v1.html to inject the snippet
st.components.v1.html(segment_js_snippet, height=0, width=0) # Height and width can be 0 as it's just code

# --- End Segment analytics.js Initialization ---


# --- Custom CSS to fix selectbox cursor behavior ---
st.markdown("""
    <style>
    /* Add this to address cursor jumping issue in selectbox for better UX */
    .stSelectbox div[data-baseweb="select"] > div:first-child {
        height: auto !important;
        min-height: 38px;
    }
    </style>
    """, unsafe_allow_html=True)
# --- End Custom CSS ---


# --- OpenAI Resources Setup ---
@st.cache_resource
def setup_openai_resources():
    client = OpenAI(api_key=st.secrets["openai_api_key"])
    config = load_config()

    file_id = config.get("file_id")
    vector_store_id = config.get("vector_store_id")
    assistant_id_checklist = config.get("assistant_id_checklist") # New: for checklist assistant
    assistant_id_advice = config.get("assistant_id_advice")       # New: for advice assistant

    try:
        # Step 1: Upload the file if not already uploaded
        if not file_id:
            with open("research.pdf", "rb") as f:
                uploaded_file = client.files.create(file=f, purpose="assistants")
            file_id = uploaded_file.id
            config["file_id"] = file_id
            print(f"File uploaded: {file_id}")

        # Step 2: Create a vector store and link the file if not already done
        if not vector_store_id:
            vector_store = client.vector_stores.create(name="Vehicle Inspection Guide")
            client.vector_stores.file_batches.create(
                vector_store_id=vector_store.id, file_ids=[file_id]
            )
            vector_store_id = vector_store.id
            config["vector_store_id"] = vector_store_id
            print(f"Vector store created and file added: {vector_store_id}")
        
        # Step 3: Create or retrieve the Checklist Assistant
        if not assistant_id_checklist:
            checklist_assistant = client.beta.assistants.create(
                name="CAMANDA Vehicle Checklist Generator",
                instructions=SYSTEM_PROMPT_CHECKLIST, # Use global constant
                model="gpt-4o",
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
            )
            assistant_id_checklist = checklist_assistant.id
            config["assistant_id_checklist"] = assistant_id_checklist
            print(f"Checklist Assistant created: {assistant_id_checklist}")
        else:
            # Optional: Update the assistant if instructions or tools change
            # This helps ensure your assistant always uses the latest prompt/tools.
            client.beta.assistants.update(
                assistant_id=assistant_id_checklist,
                instructions=SYSTEM_PROMPT_CHECKLIST,
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
            )
            print(f"Using existing Checklist Assistant: {assistant_id_checklist}")

        # Step 4: Create or retrieve the Advice Assistant
        if not assistant_id_advice:
            advice_assistant = client.beta.assistants.create(
                name="Trip Advice Generator",
                instructions=SYSTEM_PROMPT_ADVICE, # Use global constant
                model="gpt-4o",
            )
            assistant_id_advice = advice_assistant.id
            config["assistant_id_advice"] = assistant_id_advice
            print(f"Advice Assistant created: {assistant_id_advice}")
        else:
            # Optional: Update the assistant if instructions change
            client.beta.assistants.update(
                assistant_id=assistant_id_advice,
                instructions=SYSTEM_PROMPT_ADVICE
            )
            print(f"Using existing Advice Assistant: {assistant_id_advice}")


        save_config(config) # Save the updated config

        # Return all necessary IDs
        return client, file_id, vector_store_id, assistant_id_checklist, assistant_id_advice

    except Exception as e:
        st.error(f"Error setting up OpenAI resources: {e}")
        return None, None, None, None, None # Return None for all on error

# Ensure `client` and `vector_store_id` (and new assistant IDs) are retrieved globally
client, file_id, vector_store_id, assistant_id_checklist, assistant_id_advice = setup_openai_resources()

if client is None:
    st.error("Failed to initialize OpenAI resources. Please check your API key and file setup.")
    st.stop() # Stop the app if resources aren't ready
# --- End OpenAI Resources Setup ---


# --- LLM Interaction Functions ---
def get_checklist_from_openai(user_trip_details, vector_store_id, assistant_id_checklist):
    if not vector_store_id:
        st.error("Vector store not set up. Cannot generate checklist.")
        return None, None # Modified: Return None for checklist and None for tokens

    try:
        # Create a thread
        empty_thread = client.beta.threads.create()
        thread_id = empty_thread.id

        # Add the user's message to the thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_trip_details,
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id_checklist # Use the passed ID
        )

        # Wait for the run to complete
        with st.spinner("Processing..."):
            while run.status in ['queued', 'in_progress', 'cancelling']:
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )

            if run.status == 'completed':
                messages = client.beta.threads.messages.list(
                    thread_id=thread_id
                )
                
                # --- START OF TOKEN USAGE EXTRACTION ---
                # Token usage is available in the 'run' object after it's completed
                prompt_tokens = run.usage.prompt_tokens if run.usage else 0
                completion_tokens = run.usage.completion_tokens if run.usage else 0
                total_tokens = run.usage.total_tokens if run.usage else 0

                token_usage_info = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
                # --- END OF TOKEN USAGE EXTRACTION ---

                for msg in messages.data:
                    if msg.role == "assistant":
                        for content_block in msg.content:
                            if content_block.type == 'text':
                                try:
                                    json_str = content_block.text.value.strip()
                                    json_str = json_str.replace('```json', '').replace('```', '').strip()
                                    checklist_dict_or_list = json.loads(json_str) # Rename variable for clarity

                                    # Defensive check: If LLM returns a single object instead of an array, wrap it
                                    if isinstance(checklist_dict_or_list, dict):
                                        checklist_dict_or_list = [checklist_dict_or_list] # Wrap single group in a list

                                    full_checklist = FullChecklist.model_validate(checklist_dict_or_list)
                                    
                                    return full_checklist, token_usage_info
                                except json.JSONDecodeError as e:
                                    st.error(f"Failed to parse checklist from LLM response: {e}. Raw response: {content_block.text.value}")
                                    return None, None # Modified: Return None for tokens on error
                                except ValidationError as e: # Catch Pydantic validation error specifically
                                    st.error(f"LLM response failed Pydantic validation: {e}. Raw response: {content_block.text.value}")
                                    return None, None
                            elif content_block.type == 'tool_calls':
                                for tool_call in content_block.tool_calls:
                                    if tool_call.type == 'function' and tool_call.function.name == "create_checklist":
                                        try:
                                            tool_args_str = tool_call.function.arguments
                                            tool_args = json.loads(tool_args_str)
                                            
                                            # Defensive check for tool call arguments too
                                            if isinstance(tool_args, dict):
                                                tool_args = [tool_args]

                                            full_checklist = FullChecklist.model_validate(tool_args)
                                            
                                            return full_checklist, token_usage_info
                                        except json.JSONDecodeError as e:
                                            st.error(f"Failed to parse tool call arguments: {e}. Raw args: {tool_args_str}")
                                            return None, None
                                        except ValidationError as e: # Catch Pydantic validation error specifically
                                            st.error(f"Tool call arguments failed Pydantic validation: {e}. Raw args: {tool_args_str}")
                                            return None, None
                                        except Exception as e:
                                            st.error(f"Error validating checklist from tool call: {e}")
                                            return None, None
                        
                st.error("Assistant did not provide a valid checklist in text or tool call.")
                return "Could not generate checklist.", None # Modified: Return None for checklist and None for tokens

            else:
                st.error(f"Assistant run failed with status: {run.status}")
                return "Assistant run failed.", None # Modified: Return None for checklist and None for tokens

    except Exception as e:
        st.error(f"An error occurred during checklist generation: {e}")
        return f"An error occurred: {e}", None # Modified: Return None for checklist and None for tokens


def generate_trip_advice(submitted_form_data: Dict[str, str], checklist_data: FullChecklist, assistant_id_advice: str) -> tuple[str, Optional[Dict[str, int]]]:
    """
    Generates trip advice based on submitted form data and checklist data using an OpenAI Assistant.
    Returns the advice content and token usage information.
    """
    try:
        empty_thread = client.beta.threads.create()
        thread_id = empty_thread.id

        user_message_content = f"""
        Based on the following vehicle inspection checklist data and submitted results, provide comprehensive and actionable trip preparation and maintenance advice.
        
        # Checklist Data: {json.dumps(checklist_data.model_dump(), indent=2)}
        # Submitted Results: {json.dumps(submitted_form_data, indent=2)}
        """
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message_content,
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id_advice # Use the passed ID
        )
        
        # Wait for the run to complete
        with st.spinner("Generating trip advice..."):
            while run.status in ['queued', 'in_progress', 'cancelling']:
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )

            if run.status == 'completed':
                messages = client.beta.threads.messages.list(
                    thread_id=thread_id
                )
                
                # --- START OF TOKEN USAGE EXTRACTION ---
                prompt_tokens = run.usage.prompt_tokens if run.usage else 0
                completion_tokens = run.usage.completion_tokens if run.usage else 0
                total_tokens = run.usage.total_tokens if run.usage else 0

                token_usage_info = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
                # --- END OF TOKEN USAGE EXTRACTION ---

                for msg in messages.data:
                    if msg.role == "assistant":
                        for content_block in msg.content:
                            if content_block.type == 'text':
                                return content_block.text.value, token_usage_info
                st.error("Assistant did not provide trip advice.")
                return "Could not generate trip advice.", None # Modified: Return None for tokens

            else:
                st.error(f"Assistant run for advice failed with status: {run.status}")
                return "Failed to generate trip advice.", None # Modified: Return None for tokens

    except Exception as e:
        st.error(f"An error occurred during trip advice generation: {e}")
        return f"An error occurred: {e}", None # Modified: Return None for tokens
# --- End LLM Interaction Functions ---


# --- Streamlit UI Layout ---
st.set_page_config(layout="wide", page_icon="🚗", page_title="CAMANDA Vehicle Trip Checklist Generator")
st.title("🚗 CAMANDA Vehicle Trip Checklist Generator")

# Pre-inspection Form
if not st.session_state.pre_inspection_form_submitted:
    with st.form("pre_inspection_form"):
        st.subheader("Pre-Inspection Details")
        user_name = st.text_input("Your Name:", value=st.session_state.get('user_name', ''))
        user_email = st.text_input("Your Email:", value=st.session_state.get('user_email', ''))
        vehicle_plate_number = st.text_input("Vehicle Plate Number:", value=st.session_state.get('vehicle_plate_number', ''))

        submitted = st.form_submit_button("Start Inspection")
        if submitted:
            if user_name and user_email and vehicle_plate_number:
                st.session_state.user_name = user_name
                st.session_state.user_email = user_email
                st.session_state.vehicle_plate_number = vehicle_plate_number
                st.session_state.pre_inspection_form_submitted = True
                
                # Identify the user with their actual name and email
                analytics.identify(
                    user_id=st.session_state.session_id,
                    traits={
                        'userID': st.session_state.user_anonymous_id,
                        'name': st.session_state.user_name,
                        'email': st.session_state.user_email
                    }
                )

                # Track an event related to this submission
                analytics.track(
                    user_id=st.session_state.user_anonymous_id,
                    event='Pre-Inspection Form Submitted',
                    properties={
                        'user_name': st.session_state.user_name,
                        'user_email': st.session_state.user_email,
                        'vehicle_plate_number': st.session_state.vehicle_plate_number,
                        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                    }
                )
                st.rerun() # Rerun to display welcome message and proceed
            else:
                st.warning("Please fill in all pre-inspection details to start.")
else:
    # Main app content after pre-inspection form (and temporary welcome message)
    # --- Section 1: Generate Checklist Input (Visible initially after pre-form) ---
    if st.session_state.show_generate_input:
        st.markdown("---")
        st.success(f"Welcome, {st.session_state.user_name}! Vehicle: {st.session_state.vehicle_plate_number}")
        st.subheader("Your Trip Request")
        actual_input = st.text_area(
            "Describe your trip or vehicle requirements:",
            height=100,
            # placeholder="e.g., 'Planning a road trip from Lagos to Abuja in a sedan', 'Need a checklist for motorcycle pre-ride inspection', 'Pre-purchase inspection checklist for a used SUV'",
            value=st.session_state.get('last_user_input', '')
        )

        if st.button("Generate Checklist", key=f"generate_button_{st.session_state.form_reset_trigger}"):
            if actual_input:
                st.session_state.last_user_input = actual_input # Save input across reruns
                # Track 'System Prompted'
                analytics.track(
                    user_id=st.session_state.user_anonymous_id, # Use persistent anonymous ID
                    event='System Prompted',
                    properties={
                        'app_name': 'Vehicle Trip Checklist Generator',
                        'prompt_type': 'Generate Checklist',
                        'user_prompt': actual_input,
                        'prompt_text_length': len(actual_input),
                        'session_id': st.session_state.session_id, # Pass session_id as a property
                        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                    }
                )
                with st.spinner("Generating your comprehensive checklist..."):
                    st.session_state.checklist_data, token_usage_checklist = get_checklist_from_openai(actual_input, vector_store_id, assistant_id_checklist)
                    
                    if st.session_state.checklist_data is not None:
                        if not st.session_state.checklist_data.root: # Empty checklist from LLM (out-of-scope)
                            st.error("Your request was not related to vehicle inspection or trip preparation. Please enter a vehicle-related query.")
                            # Keep show_generate_input true to allow re-entry
                            # Other flags remain false, so the section stays visible.
                            st.session_state.checklist_data = None
                            st.session_state.selectbox_indices = {}
                            st.session_state.generated_pdf_path = None
                            st.session_state.generated_pdf_temp_dir = None
                            st.session_state.trip_advice_content = None # Clear any previous advice
                        else:
                            # ADDITION FOR TOKEN LOGGING AND SESSION TOTAL
                            if token_usage_checklist:
                                st.session_state.total_session_tokens += token_usage_checklist['total_tokens']

                            # Track 'Checklist Generated'
                            analytics.track(
                                user_id=st.session_state.user_anonymous_id, # Use persistent anonymous ID
                                event='Checklist Generated',
                                properties={
                                    'app_name': 'Vehicle Trip Checklist Generator',
                                    'number_of_groups': len(st.session_state.checklist_data.root),
                                    'total_checklist_items': sum(len(g.Checklist) for g in st.session_state.checklist_data.root),
                                    'llm_model_used': 'gpt-4o', # Hardcoded as per your client config
                                    'llm_prompt_tokens': token_usage_checklist['prompt_tokens'] if token_usage_checklist else 0,
                                    'llm_completion_tokens': token_usage_checklist['completion_tokens'] if token_usage_checklist else 0,
                                    'llm_total_tokens': token_usage_checklist['total_tokens'] if token_usage_checklist else 0,
                                    'total_session_tokens_so_far': st.session_state.total_session_tokens,
                                    'session_id': st.session_state.session_id, # Pass session_id as a property
                                    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                                }
                            )
                            # Transition to checklist overview state
                            st.session_state.show_generate_input = False
                            st.session_state.show_checklist_overview = True
                            st.session_state.show_inspection_form_actual = False
                            st.session_state.show_report_section = False
                            
                            # Initialize selectbox_indices for the upcoming inspection form
                            st.session_state.selectbox_indices = {
                                f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}": 0
                                for group in st.session_state.checklist_data.root
                                for item in group.Checklist
                            }
                    st.session_state.form_reset_trigger += 1
                    st.rerun() # Rerun to update UI based on new state
            else:
                st.warning("Please describe your trip to generate a checklist.")
    
    # --- Section 2: Checklist Overview and Start Inspection Button (Screenshot 2025-07-29 152313.png) ---
    if st.session_state.show_checklist_overview and st.session_state.checklist_data:
        st.markdown("---")
        st.subheader("Generated Checklist Overview")
        st.write("A comprehensive checklist has been generated based on your request.")
        for group in st.session_state.checklist_data.root:
            st.markdown(f"### {group.GroupName}")
            for item in group.Checklist:
                st.markdown(
                    f"- {item.ChecklistName} (Type: <span style='color:green; font-weight:bold;'>{item.ChecklistType}</span>)",
                    unsafe_allow_html=True
                )
       
        
        st.markdown("---") # Separator before the button
        if st.button("Start Inspection", key="start_inspection_button"):
            # Transition to actual inspection form state
            st.session_state.show_checklist_overview = False
            st.session_state.show_inspection_form_actual = True
            st.session_state.show_report_section = False
            st.session_state.start_inspection_time = datetime.datetime.utcnow() # Record start time
            # Track 'Inspection Started'
            analytics.track(
                user_id=st.session_state.user_anonymous_id, # Use persistent anonymous ID
                event='Inspection Started',
                properties={
                    'app_name': 'Vehicle Trip Checklist Generator',
                    'checklist_id': 'Generated Checklists',
                    'vehicle_plate_number': st.session_state.vehicle_plate_number,
                    'session_id': st.session_state.session_id, # Pass session_id as a property
                    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                }
            )
            st.rerun() # Rerun to display the form

    # --- Section 3: Actual Inspection Form (with selectboxes) ---
    if st.session_state.show_inspection_form_actual and st.session_state.checklist_data:
        st.markdown("---")
        st.subheader("Perform Your Inspection")

        with st.form("inspection_form", clear_on_submit=False):
            for group in st.session_state.checklist_data.root:
                st.markdown(f"#### {group.GroupName}")
                for item in group.Checklist:
                    key = f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}"
                    options = ["Select Status", "Pass", "Fail", "N/A (Not Applicable)"]
                    
                    current_index = st.session_state.selectbox_indices.get(key, 0)
                    
                    selected_option_index = st.selectbox(
                        f"**{item.ChecklistSerialNo}.** {item.ChecklistName}",
                        options,
                        index=current_index,
                        key=key # Use the unique key
                    )
                    st.session_state.selectbox_indices[key] = options.index(selected_option_index)

            submitted_form = st.form_submit_button("Submit Inspection Form")
            if submitted_form:
                form_data = {}
                for group in st.session_state.checklist_data.root:
                    for item in group.Checklist:
                        key = f"{group.GroupId}_{item.ChecklistId}_{item.ChecklistSerialNo}"
                        form_data[key] = options[st.session_state.selectbox_indices[key]]

                with st.spinner("Submitting inspection results and generating report..."):
                    # Clear selectbox indices after submission if not needed for re-display
                    st.session_state.selectbox_indices = {} 
                    st.session_state.form_reset_trigger += 1 # Important for form keying

                    st.session_state.submitted_form_data = form_data
                    
                    completion_duration_minutes = None
                    if st.session_state.start_inspection_time:
                        end_time = datetime.datetime.utcnow()
                        duration = end_time - st.session_state.start_inspection_time
                        completion_duration_minutes = duration.total_seconds() / 60

                    # Calculate summary percentages for analytics and PDF generation
                    summary_percentages = pdf_service._calculate_summary_percentages(
                        st.session_state.checklist_data,
                        st.session_state.submitted_form_data
                    )

                    # Track 'User Submitted Checklist'
                    analytics.track(
                        user_id=st.session_state.user_anonymous_id, # Use persistent anonymous ID
                        event='User Submitted Checklist',
                        properties={
                            'app_name': 'Vehicle Trip Checklist Generator',
                            'checklist_id': 'Generated Checklists',
                            'vehicle_plate_number': st.session_state.vehicle_plate_number,
                            'total_items_completed': summary_percentages['passed_count'],
                            'total_items_skipped': summary_percentages['skipped_count'],
                            'total_items_failed': summary_percentages['failed_count'],
                            'completion_duration_minutes': completion_duration_minutes,
                            'overall_status': 'Completed' if (summary_percentages['passed_count'] + summary_percentages['failed_count'] + summary_percentages['skipped_count'] == summary_percentages['total_items']) else 'Partial Completion',
                            'session_id': st.session_state.session_id, # Pass session_id as a property
                            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                        }
                    )
                    st.session_state.start_inspection_time = None # Reset for next inspection

                    # Generate trip advice (needed for PDF content)
                    st.session_state.trip_advice_content, token_usage_advice = generate_trip_advice(
                        st.session_state.submitted_form_data,
                        st.session_state.checklist_data,
                        assistant_id_advice # Pass the advice assistant ID
                    )

                    # ADDITION FOR TOKEN LOGGING AND SESSION TOTAL
                    if token_usage_advice:
                        st.session_state.total_session_tokens += token_usage_advice['total_tokens']

                    # Determine summary outcome
                    summary_outcome = "All Clear!" if "All Clear!" in st.session_state.trip_advice_content else "Caution Needed"
                    
                    # Track 'System Generated Checklist Summary'
                    analytics.track(
                        user_id=st.session_state.user_anonymous_id, # Use persistent anonymous ID
                        event='System Generated Checklist Summary',
                        properties={
                            'app_name': 'Vehicle Trip Checklist Generator',
                            'checklist_id': 'Generated Checklists',
                            'vehicle_plate_number': st.session_state.vehicle_plate_number,
                            'summary_outcome': summary_outcome,
                            'issues_identified': summary_outcome == "Caution Needed",
                            'number_of_failed_items_in_summary': summary_percentages['failed_count'],
                            'number_of_skipped_items_in_summary': summary_percentages['skipped_count'],
                            'llm_prompt_tokens': token_usage_advice['prompt_tokens'] if token_usage_advice else 0,
                            'llm_completion_tokens': token_usage_advice['completion_tokens'] if token_usage_advice else 0,
                            'llm_total_tokens': token_usage_advice['total_tokens'] if token_usage_advice else 0,
                            'total_session_tokens_so_far': st.session_state.total_session_tokens, # New property
                            'session_id': st.session_state.session_id, # Pass session_id as a property
                            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                        }
                    )
                    # END ADDITION

                    # Generate PDF report
                    temp_dir = tempfile.mkdtemp()
                    pdf_file_name = f"Inspection_Report_{st.session_state.vehicle_plate_number}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    logo_file_path = os.path.join(os.path.dirname(__file__), "logo.png")
                    pdf_path = os.path.join(temp_dir, pdf_file_name)

                    st.session_state.generated_pdf_path = generate_inspection_pdf(
                        user_name=st.session_state.user_name,
                        user_email=st.session_state.user_email,
                        vehicle_plate_number=st.session_state.vehicle_plate_number,
                        checklist_data=st.session_state.checklist_data,
                        submitted_form_data=st.session_state.submitted_form_data,
                        trip_advice_content=st.session_state.trip_advice_content,
                        logo_path=logo_file_path,
                        file_name=pdf_path
                    )
                    st.session_state.generated_pdf_temp_dir = temp_dir

                    # Transition to report section
                    st.session_state.show_inspection_form_actual = False
                    st.session_state.show_report_section = True
                    st.rerun()

    # --- Section 4: Inspection Report ---
    if st.session_state.show_report_section:
        st.markdown("---")
        if st.session_state.generated_pdf_path:
            st.success("Inspection report generated successfully!")
            
            # Display advice directly in the app before download
            if st.session_state.trip_advice_content:
                st.markdown("### Trip Preparation Advice")
                st.write(st.session_state.trip_advice_content)
                st.markdown("---")

            with open(st.session_state.generated_pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="Download Inspection Report PDF",
                    data=pdf_file,
                    file_name=os.path.basename(st.session_state.generated_pdf_path),
                    mime="application/pdf",
                    key="download_pdf_button"
                )
            # Track 'Report Downloaded'
            analytics.track(
                user_id=st.session_state.user_anonymous_id, # Use persistent anonymous ID
                event='Report Downloaded',
                properties={
                    'app_name': 'Vehicle Trip Checklist Generator',
                    'checklist_id': 'Generated Checklists',
                    'vehicle_plate_number': st.session_state.vehicle_plate_number,
                    'session_id': st.session_state.session_id, # Pass session_id as a property
                    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                }
            )

            # --- Start New Session Button ---
            if st.button("Start New Session", key="start_new_session_final_button"):
                # Log final session tokens before resetting
                if st.session_state.total_session_tokens > 0:
                    analytics.track(
                        user_id=st.session_state.session_id,
                        event='Session Concluded - Total Tokens Used',
                        properties={
                            'app_name': 'Vehicle Trip Checklist Generator',
                            'total_session_llm_tokens': st.session_state.total_session_tokens,
                            'session_id': st.session_state.session_id, # Pass session_id as a property
                            'name': st.session_state.user_name,
                            'email': st.session_state.user_email,
                            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                        }
                    )
                # Reset all relevant session states for a clean restart
                for key in ['show_generate_input', 'show_checklist_overview', 'show_inspection_form_actual',
                            'show_report_section', 'checklist_data', 'selectbox_indices',
                            'submitted_form_data', 'pre_inspection_form_submitted', 'user_name',
                            'user_email', 'vehicle_plate_number', 'generated_pdf_path',
                            'generated_pdf_temp_dir', 'last_user_input', 'total_session_tokens',
                            'start_inspection_time', 'trip_advice_content', 'show_welcome_message_temporary',
                            'session_id', 'user_anonymous_id']:
                    if key in st.session_state:
                        del st.session_state[key]
                
                # Explicitly set initial UI states
                st.session_state.show_generate_input = True
                st.session_state.show_checklist_overview = False
                st.session_state.show_inspection_form_actual = False
                st.session_state.show_report_section = False
                st.session_state.form_reset_trigger += 1 # Increment to ensure form resets
                st.rerun()
            # --- End Start New Session Button ---

        else:
            st.error("Failed to generate PDF report.")