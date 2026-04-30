"""
RoofDraftAI - Tools Routes
"""
import os
from datetime import date

from anthropic import Anthropic
from flask import Blueprint, jsonify, request

from database.db import get_total_generations, log_generation, require_auth, save_draft

tools_bp = Blueprint('tools', __name__)

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2600


TOOL_ACCESS = {
    "free": ["proposal"],
    "starter": ["proposal"],
    "pro": ["proposal", "followup", "review", "referral"],
    "admin": ["proposal", "followup", "review", "referral"],
}

FREE_LIMIT = 1
PAYING_PLANS = {"starter", "pro"}


def is_paying(user):
    return bool(user.get("is_admin")) or user.get("plan", "free") in PAYING_PLANS


def check_access(user, tool_name):
    """Return (allowed: bool, error_message: str | None)."""
    if user.get("is_admin"):
        return True, None

    plan = user.get("plan", "free")
    allowed_tools = TOOL_ACCESS.get(plan, ["proposal"])
    if tool_name not in allowed_tools:
        return False, "This tool requires the Pro plan. Upgrade to unlock all 4 tools."

    if plan == "free" and get_total_generations(user["id"]) >= FREE_LIMIT:
        return False, "Your free trial proposal has already been used. Upgrade to keep generating client-ready roofing documents."

    return True, None


def auth_and_check(tool_name):
    """Authenticate request and check plan access. Return (user, error_response)."""
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    allowed, msg = check_access(user, tool_name)
    if not allowed:
        return None, (jsonify({"error": msg}), 403)

    return user, None


def value(data, *keys, default=""):
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return default


def build_full_address(address, city, state, zip_code):
    parts = [address, city, state, zip_code]
    return ", ".join(part for part in parts if part)


def clean_list(values):
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def clean_dict(value):
    return value if isinstance(value, dict) else {}


def present(text):
    return bool(str(text).strip()) if text is not None else False


def present_list(values):
    return bool(values)


def has_roof_visual_content(roof_visual):
    return any(
        [
            roof_visual.get("hasImage"),
            present(roof_visual.get("visualType")),
            present_list(roof_visual.get("labels", [])),
            present(roof_visual.get("customLabel")),
            present(roof_visual.get("estimatedRoofArea")),
            present(roof_visual.get("estimatedSquares")),
            present(roof_visual.get("pitchNote")),
            present(roof_visual.get("rakeNote")),
            present(roof_visual.get("gutterLengthNote")),
            present(roof_visual.get("wasteFactorNote")),
            present(roof_visual.get("measurementSource")),
            present(roof_visual.get("customMeasurementSource")),
            present(roof_visual.get("measurementNotes")),
            present(roof_visual.get("summaryNotes")),
        ]
    )


@tools_bp.route("/api/tools/proposal", methods=["POST"])
def proposal():
    user, err = auth_and_check("proposal")
    if err:
        return err

    data = request.get_json() or {}

    customer_name = value(data, "customer_name", "homeowner_name")
    customer_email = value(data, "customer_email")
    customer_phone = value(data, "customer_phone")
    customer_address = value(data, "customer_address", "property_address")
    customer_city = value(data, "customer_city")
    customer_state = value(data, "customer_state")
    customer_zip = value(data, "customer_zip")

    company_name = value(data, "company_name", "roofing_company_name")
    contractor_name = value(data, "contractor_name", "owner_name")
    contractor_phone = value(data, "contractor_phone", "company_phone")
    contractor_email = value(data, "contractor_email", "company_email")
    company_website = value(data, "company_website")
    company_address = value(data, "company_address")
    license_number = value(data, "license_number")
    service_area = value(data, "service_area")

    job_type = value(data, "job_type", "roof_type")
    roof_size_squares = value(data, "roof_size_squares", "square_footage")
    existing_roof_material = value(data, "existing_roof_material")
    proposed_material = value(data, "proposed_material", "materials")
    material_brand = value(data, "material_brand")
    roof_pitch = value(data, "roof_pitch", "pitch")
    number_of_layers = value(data, "number_of_layers")
    decking_notes = value(data, "decking_notes")

    scope_items = clean_list(data.get("scope_items"))
    scope_notes = value(data, "scope_notes", "scope")

    price_total = value(data, "price_total", "estimated_project_total")
    deposit_required = value(data, "deposit_required", "deposit_requirement")
    payment_terms = value(data, "payment_terms")
    financing_note = value(data, "financing_note")

    start_date = value(data, "start_date", "estimated_start_date")
    completion_days = value(data, "completion_days", "estimated_duration")
    weather_delay_note = value(data, "weather_delay_note")

    warranty_labor = value(data, "warranty_labor", "workmanship_warranty")
    warranty_materials = value(data, "warranty_materials", "manufacturer_warranty")
    warranty_notes = value(data, "warranty_notes")
    cleanup_language = value(data, "cleanup_language")
    tone = value(data, "tone", "proposal_tone", default="Professional")
    output_version = value(data, "output_version", default="full_proposal")

    roof_visual = clean_dict(data.get("roof_visual"))
    roof_visual_enabled = bool(roof_visual.get("enabled"))
    roof_visual_has_image = bool(roof_visual.get("hasImage") or roof_visual.get("imageName"))
    roof_visual_type = value(roof_visual, "visualType")
    roof_visual_labels = clean_list(roof_visual.get("labels"))
    roof_visual_custom_label = value(roof_visual, "customLabel")
    if "Other" in roof_visual_labels:
        roof_visual_labels = [label for label in roof_visual_labels if label != "Other"]
        if roof_visual_custom_label:
            roof_visual_labels.append(roof_visual_custom_label)
        else:
            roof_visual_labels.append("Other")

    roof_visual_estimated_area = value(roof_visual, "estimatedRoofArea")
    roof_visual_estimated_squares = value(roof_visual, "estimatedSquares")
    roof_visual_pitch_note = value(roof_visual, "pitchNote")
    roof_visual_rake_note = value(roof_visual, "rakeNote")
    roof_visual_gutter_note = value(roof_visual, "gutterLengthNote")
    roof_visual_waste_factor = value(roof_visual, "wasteFactorNote")
    roof_visual_measurement_source = value(roof_visual, "measurementSource")
    if roof_visual_measurement_source == "Other":
        roof_visual_measurement_source = value(roof_visual, "customMeasurementSource", default="Other")
    roof_visual_measurement_notes = value(roof_visual, "measurementNotes")
    roof_visual_summary_notes = value(roof_visual, "summaryNotes")
    roof_visual_explanation_style = value(
        roof_visual,
        "explanationStyle",
        default="Simple homeowner explanation",
    )
    roof_visual_included = roof_visual_enabled and has_roof_visual_content(roof_visual)

    today_str = date.today().strftime("%B %d, %Y")
    full_address = build_full_address(customer_address, customer_city, customer_state, customer_zip)
    scope_block = "\n".join(f"- {item}" for item in scope_items) if scope_items else "- Use the additional scope notes only."
    roof_visual_labels_block = "\n".join(f"- {item}" for item in roof_visual_labels) if roof_visual_labels else "- None provided."
    roof_visual_measurement_block = "\n".join(
        [
            f"- Estimated Roof Area: {roof_visual_estimated_area or 'Not provided'}",
            f"- Estimated Squares: {roof_visual_estimated_squares or 'Not provided'}",
            f"- Pitch Note: {roof_visual_pitch_note or 'Not provided'}",
            f"- Rake Note: {roof_visual_rake_note or 'Not provided'}",
            f"- Gutter Length Note: {roof_visual_gutter_note or 'Not provided'}",
            f"- Waste Factor Note: {roof_visual_waste_factor or 'Not provided'}",
            f"- Measurement Source: {roof_visual_measurement_source or 'Not provided'}",
            f"- Additional Measurement Notes: {roof_visual_measurement_notes or 'Not provided'}",
        ]
    )

    user_prompt = f"""Write polished roofing sales copy using only the information provided. Do not invent measurements, pricing, warranties, timelines, licensing, financing, or legal claims that were not supplied.

TODAY'S DATE: {today_str}. Use this if you include a date.
TONE: {tone}
OUTPUT VERSION: {output_version}

If OUTPUT VERSION is "full_proposal":
- Return a homeowner-ready roofing proposal in clean markdown.
- Use section headings when data exists: Proposal Title, Prepared For, Prepared By, Project Summary, Scope of Work, Materials, Timeline, Warranty, Cleanup and Site Care, Investment, Payment Terms, Next Steps, Closing.
- Use bullet points inside Scope of Work and Materials when that improves clarity.
- Keep the language practical, professional, and easy to trust.
- If a field is missing, omit it gracefully instead of filling in fake specifics.

If OUTPUT VERSION is "short_summary":
- Return a concise customer-ready summary under 250 words using markdown headings.

If OUTPUT VERSION is "customer_email":
- Return:
  Subject Line:
  Email:
- The email should sound ready to send and mention the proposal naturally.

If contractor-guided roof visual information is provided:
- Add a section titled "Roof Visual Overview".
- Treat all visual labels, measurement notes, and scope markers as contractor-provided notes.
- Never say the software detected, measured, outlined, verified, or confirmed anything automatically.
- If an image is attached, refer to it as a contractor-provided roof visual included for proposal clarity.
- Include the visual type when provided.
- Include a "Contractor-Provided Visual Notes" subsection when labels or summary notes are provided.
- Include a "Measurement Context" subsection when any roof area, squares, pitch, rake, gutter, waste factor, measurement source, or measurement note is provided.
- Use the selected explanation style to write a homeowner-friendly explanation paragraph.
- If Measurement Source is "Visual estimate only", make it clear the measurements should be verified before ordering materials or acceptance.
- Include this exact disclaimer at the end of the section: "Visual notes are provided for clarity only. Final measurements, pitch, material quantities, local requirements, warranty terms, and pricing should be verified by the contractor before sending or acceptance."
- Do not include the Roof Visual Overview section at all if no visual information is provided.

INPUTS
Customer Name: {customer_name}
Customer Email: {customer_email}
Customer Phone: {customer_phone}
Property Address: {full_address}

Company Name: {company_name}
Contact Name: {contractor_name}
Company Phone: {contractor_phone}
Company Email: {contractor_email}
Company Website: {company_website}
Company Address: {company_address}
License Number: {license_number}
Service Area: {service_area}

Job Type: {job_type}
Roof Size / Squares: {roof_size_squares}
Existing Roof Material: {existing_roof_material}
Proposed Material: {proposed_material}
Material Brand: {material_brand}
Roof Pitch: {roof_pitch}
Number of Layers: {number_of_layers}
Decking Notes: {decking_notes}

Scope Checklist:
{scope_block}

Additional Scope Notes:
{scope_notes}

Estimated Project Total: {price_total}
Deposit Requirement: {deposit_required}
Payment Terms: {payment_terms}
Financing Note: {financing_note}

Estimated Start Date: {start_date}
Estimated Duration: {completion_days}
Weather Delay Note: {weather_delay_note}

Workmanship Warranty: {warranty_labor}
Manufacturer Warranty: {warranty_materials}
Warranty Notes: {warranty_notes}
Cleanup Language: {cleanup_language}

ROOF VISUAL OVERVIEW PROVIDED: {"Yes" if roof_visual_included else "No"}
Roof Visual Enabled In Proposal: {"Yes" if roof_visual_enabled else "No"}
Roof Visual Image Attached In Proposal Preview: {"Yes" if roof_visual_has_image else "No"}
Roof Visual Type: {roof_visual_type or "Not provided"}
Roof Visual Explanation Style: {roof_visual_explanation_style}

Contractor-Provided Visual Labels:
{roof_visual_labels_block}

Measurement Context:
{roof_visual_measurement_block}

Visual Summary Notes:
{roof_visual_summary_notes or "Not provided"}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You are a professional proposal writer for roofing contractors. Write clear, homeowner-ready documents that feel polished and practical. Never invent missing facts, guarantees, legal language, automatic measurements, or visual detections. If roof visual information is provided, treat it as contractor-guided proposal clarity only.",
            messages=[{"role": "user", "content": user_prompt}],
        )
        result = message.content[0].text
        log_generation(user["id"], "proposal")
        draft_id = None
        if is_paying(user):
            title = f"Proposal - {customer_name}" + (f", {full_address}" if full_address else "")
            draft_id = save_draft(user["id"], "proposal", title[:255], result)
        return jsonify({"result": result, "tool": "proposal", "draft_id": draft_id})
    except Exception as exc:
        print(f"[Tools/proposal] Error: {exc}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Generation failed - please try again"}), 500


@tools_bp.route("/api/tools/followup", methods=["POST"])
def followup():
    user, err = auth_and_check("followup")
    if err:
        return err

    data = request.get_json() or {}

    customer_name = value(data, "customer_name")
    project_type = value(data, "project_type", "job_type")
    proposal_amount = value(data, "proposal_amount")
    last_contact_date = value(data, "last_contact_date", "days_since_proposal")
    follow_up_reason = value(data, "follow_up_reason")
    notes = value(data, "notes")
    tone = value(data, "tone", default="Professional")
    contractor_name = value(data, "contractor_name")
    company_name = value(data, "company_name")
    contractor_phone = value(data, "contractor_phone")
    contractor_email = value(data, "contractor_email")

    user_prompt = f"""Write 3 follow-up options for a roofing contractor.

FORMAT:
- Label them Option A, Option B, Option C.
- For each option include:
  Subject Line:
  Email:
  Text Version:

RULES:
- Sound like a real contractor, not a generic sales template.
- Respect the requested tone: {tone}.
- Keep each email under 140 words.
- Keep each text version short enough to send comfortably by SMS.
- Use one clear next step and avoid pressure tactics.
- Do not say "just checking in."

INPUTS
Customer Name: {customer_name}
Project Type: {project_type}
Proposal Amount: {proposal_amount}
Last Contact Date or Timing: {last_contact_date}
Follow-Up Reason: {follow_up_reason}
Notes: {notes}
Contractor Name: {contractor_name}
Company Name: {company_name}
Contractor Phone: {contractor_phone}
Contractor Email: {contractor_email}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You write practical follow-up emails and text messages for roofing contractors. Keep the tone respectful, specific, and easy for a homeowner to respond to.",
            messages=[{"role": "user", "content": user_prompt}],
        )
        result = message.content[0].text
        log_generation(user["id"], "followup")
        draft_id = None
        if is_paying(user):
            title = f"Follow-Up - {customer_name}" + (f" ({project_type})" if project_type else "")
            draft_id = save_draft(user["id"], "followup", title[:255], result)
        return jsonify({"result": result, "tool": "followup", "draft_id": draft_id})
    except Exception as exc:
        print(f"[Tools/followup] Error: {exc}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Generation failed - please try again"}), 500


@tools_bp.route("/api/tools/review", methods=["POST"])
def review():
    user, err = auth_and_check("review")
    if err:
        return err

    data = request.get_json() or {}

    customer_name = value(data, "customer_name")
    job_type = value(data, "job_type")
    contractor_name = value(data, "contractor_name")
    company_name = value(data, "company_name")
    review_link = value(data, "review_link")
    tone = value(data, "tone", default="Professional")

    user_prompt = f"""Write a review request for a roofing contractor.

FORMAT:
- Email Version:
- Text Message Version:

RULES:
- Respect the requested tone: {tone}.
- The email should feel human, warm, and concise.
- The text should be short, natural, and not pushy.
- Do not offer incentives.
- If a review link exists, include it naturally.

INPUTS
Customer First Name: {customer_name}
Job Type: {job_type}
Contractor Name: {contractor_name}
Company Name: {company_name}
Review Link: {review_link}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You write review request messages for roofing contractors. Make them sound natural and respectful.",
            messages=[{"role": "user", "content": user_prompt}],
        )
        result = message.content[0].text
        log_generation(user["id"], "review")
        draft_id = None
        if is_paying(user):
            title = f"Review Request - {customer_name}" + (f" ({job_type})" if job_type else "")
            draft_id = save_draft(user["id"], "review", title[:255], result)
        return jsonify({"result": result, "tool": "review", "draft_id": draft_id})
    except Exception as exc:
        print(f"[Tools/review] Error: {exc}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Generation failed - please try again"}), 500


@tools_bp.route("/api/tools/referral", methods=["POST"])
def referral():
    user, err = auth_and_check("referral")
    if err:
        return err

    data = request.get_json() or {}

    customer_name = value(data, "customer_name")
    job_completed = value(data, "job_completed")
    contractor_name = value(data, "contractor_name")
    company_name = value(data, "company_name")
    referral_incentive = value(data, "referral_incentive")
    phone_number = value(data, "phone_number", "contractor_phone")
    tone = value(data, "tone", default="Professional")

    user_prompt = f"""Write a referral request for a roofing contractor.

FORMAT:
- Email Version:
- Text Message Version:

RULES:
- Respect the requested tone: {tone}.
- Keep the language warm, natural, and low pressure.
- If a referral incentive is provided, mention it naturally without leading with it.
- Use a clear, simple next step.

INPUTS
Customer First Name: {customer_name}
Completed Job Type: {job_completed}
Contractor Name: {contractor_name}
Company Name: {company_name}
Referral Incentive: {referral_incentive}
Contractor Phone: {phone_number}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You write referral request messages for roofing contractors. Keep them helpful, natural, and easy to send.",
            messages=[{"role": "user", "content": user_prompt}],
        )
        result = message.content[0].text
        log_generation(user["id"], "referral")
        draft_id = None
        if is_paying(user):
            title = f"Referral - {customer_name}" + (f" ({job_completed})" if job_completed else "")
            draft_id = save_draft(user["id"], "referral", title[:255], result)
        return jsonify({"result": result, "tool": "referral", "draft_id": draft_id})
    except Exception as exc:
        print(f"[Tools/referral] Error: {exc}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Generation failed - please try again"}), 500
