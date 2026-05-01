"""
RoofDraftAI generation routes.
"""

import os
import traceback
from datetime import date

from anthropic import Anthropic
from flask import Blueprint, jsonify, request

from database.db import get_total_generations, log_generation, require_auth
from extensions import auth_user_or_ip, limiter

tools_bp = Blueprint("tools", __name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2600
FREE_LIMIT = 1
PRO_MESSAGE = "This tool requires the Pro plan. Upgrade to unlock all 4 tools."
FREE_LIMIT_MESSAGE = "You've used your free proposal. Upgrade to Pro to continue."


def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("Anthropic API key not configured")
    return Anthropic(api_key=api_key)


def can_use_tool(user, tool_name):
    if bool(user.get("is_admin")):
        return True, None
    plan = user.get("plan", "free")
    if plan == "pro":
        return True, None
    if plan == "starter":
        if tool_name == "proposal":
            return True, None
        return False, PRO_MESSAGE
    if tool_name != "proposal":
        return False, PRO_MESSAGE
    generations_this_month = int(user.get("generations_this_month") or 0)
    total_generations = get_total_generations(user["id"])
    if generations_this_month >= FREE_LIMIT or total_generations >= FREE_LIMIT:
        return False, FREE_LIMIT_MESSAGE
    return True, None


def auth_and_check(tool_name):
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    allowed, message = can_use_tool(user, tool_name)
    if not allowed:
        return None, (jsonify({"error": message}), 403)
    return user, None


def text_value(data, *keys):
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def clean_list(values):
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def roof_size_squares_label(data):
    direct = text_value(data, "roof_size_squares")
    if direct:
        return direct
    square_footage = text_value(data, "square_footage")
    if not square_footage:
        return ""
    try:
        numeric = float(square_footage)
    except (TypeError, ValueError):
        return square_footage
    if numeric <= 0:
        return ""
    squares = round(numeric / 100.0, 1)
    display = int(squares) if float(squares).is_integer() else squares
    return f"{display} squares"


def roof_visual_has_content(roof_visual):
    if not isinstance(roof_visual, dict):
        return False
    fields = [
        roof_visual.get("hasImage"),
        roof_visual.get("imageName"),
        roof_visual.get("visualType"),
        roof_visual.get("customLabel"),
        roof_visual.get("estimatedSquares"),
        roof_visual.get("pitchNote"),
        roof_visual.get("rakeNote"),
        roof_visual.get("gutterLengthNote"),
        roof_visual.get("wasteFactorNote"),
        roof_visual.get("measurementSource"),
        roof_visual.get("customMeasurementSource"),
        roof_visual.get("measurementNotes"),
        roof_visual.get("summaryNotes"),
    ]
    return any(str(item).strip() if isinstance(item, str) else item for item in fields) or bool(clean_list(roof_visual.get("labels")))


def build_proposal_prompt(data):
    roof_visual = data.get("roof_visual") or {}
    roof_visual_labels = clean_list(roof_visual.get("labels"))
    if "Other" in roof_visual_labels:
        roof_visual_labels = [label for label in roof_visual_labels if label != "Other"]
        custom_label = text_value(roof_visual, "customLabel")
        if custom_label:
            roof_visual_labels.append(custom_label)

    measurement_source = text_value(roof_visual, "measurementSource")
    if measurement_source == "Other":
        measurement_source = text_value(roof_visual, "customMeasurementSource") or "Other"

    scope_items = clean_list(data.get("scope_items"))
    scope_lines = "\n".join(f"- {item}" for item in scope_items) if scope_items else ""
    labels_block = "\n".join(f"- {item}" for item in roof_visual_labels) if roof_visual_labels else "- None provided."
    measurement_lines = "\n".join(
        [
            f"- Estimated squares: {text_value(roof_visual, 'estimatedSquares') or 'Not provided'}",
            f"- Pitch note: {text_value(roof_visual, 'pitchNote') or 'Not provided'}",
            f"- Rake note: {text_value(roof_visual, 'rakeNote') or 'Not provided'}",
            f"- Gutter length note: {text_value(roof_visual, 'gutterLengthNote') or 'Not provided'}",
            f"- Waste factor note: {text_value(roof_visual, 'wasteFactorNote') or 'Not provided'}",
            f"- Measurement source: {measurement_source or 'Not provided'}",
            f"- Additional measurement notes: {text_value(roof_visual, 'measurementNotes') or 'Not provided'}",
        ]
    )
    address = ", ".join(
        [part for part in [text_value(data, "customer_address", "property_address"), text_value(data, "customer_city"), text_value(data, "customer_state"), text_value(data, "customer_zip")] if part]
    )
    today = date.today().strftime("%B %d, %Y")
    roof_visual_included = roof_visual_has_content(roof_visual)

    return f"""
Write a polished homeowner-ready roofing proposal in clean markdown using only the provided information.
Do not invent missing measurements, pitch, squares, pricing, warranty terms, payment terms, licensing details, or automatic detections.
Today's date: {today}

Required structure when information exists:
- Project Summary
- Scope of Work
- Materials
- Timeline
- Warranty
- Cleanup
- Investment
- Payment Terms
- Next Steps
- Closing

If roof visual information is provided:
- Add a section titled "Roof Visual Overview".
- Treat all labels and notes as contractor-provided.
- Never say RoofDraftAI detected, measured, verified, or confirmed anything automatically.
- Include a "Contractor-Provided Visual Notes" subsection when labels or summary notes exist.
- Include a "Measurement Context" subsection when squares, pitch, rake, gutters, waste factor, measurement source, or measurement notes exist.
- Match this explanation style: {text_value(roof_visual, "explanationStyle") or "Simple homeowner explanation"}.
- If measurement source is "Visual estimate only", clearly say those quantities should be verified before ordering materials or acceptance.
- End the section with this exact disclaimer: "Visual notes are provided for clarity only. Final measurements, pitch, material quantities, local requirements, warranty terms, and pricing should be verified by the contractor before sending or acceptance."
- Omit the Roof Visual Overview section entirely if no visual information is provided.

Customer name: {text_value(data, "customer_name", "homeowner_name")}
Customer email: {text_value(data, "customer_email")}
Customer phone: {text_value(data, "customer_phone")}
Property address: {address}

Company name: {text_value(data, "company_name")}
Your name: {text_value(data, "contractor_name", "owner_name")}
Your phone: {text_value(data, "contractor_phone", "company_phone")}
Your email: {text_value(data, "contractor_email", "company_email")}
Company website: {text_value(data, "company_website")}
Company address: {text_value(data, "company_address")}
License number: {text_value(data, "license_number")}

Job type: {text_value(data, "job_type", "roof_type")}
Square footage: {text_value(data, "square_footage")}
Roof size / squares: {roof_size_squares_label(data)}
Existing roof material: {text_value(data, "existing_roof_material")}
Proposed material: {text_value(data, "proposed_material", "materials")}
Material brand / shingle type: {text_value(data, "material_brand")}
Roof pitch: {text_value(data, "roof_pitch", "pitch")}
Number of layers: {text_value(data, "number_of_layers")}
Decking notes: {text_value(data, "decking_notes")}

Scope checklist:
{scope_lines or '- None provided'}

Additional scope notes:
{text_value(data, "scope_notes", "scope") or 'None provided'}

Estimated project total: {text_value(data, "price_total", "estimated_project_total")}
Deposit required: {text_value(data, "deposit_required", "deposit_requirement")}
Payment terms: {text_value(data, "payment_terms")}
Financing note: {text_value(data, "financing_note")}

Estimated start date: {text_value(data, "start_date", "estimated_start_date")}
Estimated duration: {text_value(data, "completion_days", "estimated_duration")}
Weather delay note: {text_value(data, "weather_delay_note")}

Labor warranty: {text_value(data, "warranty_labor", "workmanship_warranty")}
Materials warranty: {text_value(data, "warranty_materials", "manufacturer_warranty")}
Warranty notes: {text_value(data, "warranty_notes")}
Cleanup language: {text_value(data, "cleanup_language")}
Tone: {text_value(data, "tone") or "Professional"}

Roof visual provided: {"Yes" if roof_visual_included else "No"}
Roof visual image attached in proposal preview: {"Yes" if roof_visual.get("hasImage") else "No"}
Visual type: {text_value(roof_visual, "visualType") or "Not provided"}
Contractor-provided visual labels:
{labels_block}
Measurement context:
{measurement_lines}
Visual summary notes:
{text_value(roof_visual, "summaryNotes") or "Not provided"}
"""


def generate_text(prompt, system_prompt):
    client = get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


@tools_bp.route("/api/tools/proposal", methods=["POST"])
@limiter.limit("20 per hour", key_func=auth_user_or_ip)
def proposal():
    try:
        user, error_response = auth_and_check("proposal")
        if error_response:
            return error_response
        data = request.get_json() or {}
        required_fields = [
            text_value(data, "customer_name", "homeowner_name"),
            text_value(data, "customer_address", "property_address"),
            text_value(data, "job_type", "roof_type"),
            text_value(data, "roof_size_squares", "square_footage"),
            text_value(data, "roof_pitch", "pitch"),
            text_value(data, "price_total", "estimated_project_total"),
            text_value(data, "company_name"),
            text_value(data, "contractor_name", "owner_name"),
            text_value(data, "contractor_phone", "company_phone"),
        ]
        if not all(required_fields) or not (clean_list(data.get("scope_items")) or text_value(data, "scope_notes", "scope")):
            return jsonify({"error": "Please add the required job details before generating."}), 400
        prompt = build_proposal_prompt(data)
        result = generate_text(
            prompt,
            "You write polished roofing proposals for contractors. Keep the copy professional, homeowner-friendly, and practical. Never invent measurements, pricing, warranties, or automatic detections.",
        )
        log_generation(user["id"], "proposal")
        return jsonify({"result": result, "tool": "proposal"})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@tools_bp.route("/api/tools/followup", methods=["POST"])
@limiter.limit("20 per hour", key_func=auth_user_or_ip)
def followup():
    try:
        user, error_response = auth_and_check("followup")
        if error_response:
            return error_response
        data = request.get_json() or {}
        required_fields = [
            text_value(data, "customer_name"),
            text_value(data, "days_since_proposal", "last_contact_date"),
            text_value(data, "proposal_amount"),
            text_value(data, "job_type", "project_type"),
            text_value(data, "contractor_name"),
            text_value(data, "company_name"),
            text_value(data, "contractor_phone"),
        ]
        if not all(required_fields):
            return jsonify({"error": "Please add the required follow-up details before generating."}), 400

        prompt = f"""
Write a professional follow-up email for a roofing contractor.
Return:
Subject Line:
Email:
Text Version:

Customer name: {text_value(data, "customer_name")}
Days since proposal was sent: {text_value(data, "days_since_proposal", "last_contact_date")}
Proposal amount: {text_value(data, "proposal_amount")}
Job type: {text_value(data, "job_type", "project_type")}
Follow-up reason: {text_value(data, "follow_up_reason") or "Sent estimate, no response"}
Notes: {text_value(data, "notes")}
Tone: {text_value(data, "tone") or "Professional"}
Your name: {text_value(data, "contractor_name")}
Company name: {text_value(data, "company_name")}
Your phone: {text_value(data, "contractor_phone")}

Keep it respectful, short, and easy for the homeowner to reply to. Avoid pushy language.
"""
        result = generate_text(
            prompt,
            "You write professional roofing follow-up emails and text messages. Keep them clear, warm, and specific.",
        )
        log_generation(user["id"], "followup")
        return jsonify({"result": result, "tool": "followup"})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@tools_bp.route("/api/tools/review", methods=["POST"])
@limiter.limit("20 per hour", key_func=auth_user_or_ip)
def review():
    try:
        user, error_response = auth_and_check("review")
        if error_response:
            return error_response
        data = request.get_json() or {}
        required_fields = [
            text_value(data, "customer_name"),
            text_value(data, "job_type"),
            text_value(data, "contractor_name"),
            text_value(data, "company_name"),
            text_value(data, "review_link"),
        ]
        if not all(required_fields):
            return jsonify({"error": "Please add the required review-request details before generating."}), 400

        prompt = f"""
Write a Google review request for a roofing contractor.
Return:
Email Version:
Text Message Version:

Customer first name: {text_value(data, "customer_name")}
Job type: {text_value(data, "job_type")}
Your name: {text_value(data, "contractor_name")}
Company name: {text_value(data, "company_name")}
Google review link: {text_value(data, "review_link")}
Tone: {text_value(data, "tone") or "Professional"}

Keep it natural, appreciative, and easy to send.
"""
        result = generate_text(
            prompt,
            "You write natural Google review requests for roofing contractors. Keep them friendly, concise, and professional.",
        )
        log_generation(user["id"], "review")
        return jsonify({"result": result, "tool": "review"})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@tools_bp.route("/api/tools/referral", methods=["POST"])
@limiter.limit("20 per hour", key_func=auth_user_or_ip)
def referral():
    try:
        user, error_response = auth_and_check("referral")
        if error_response:
            return error_response
        data = request.get_json() or {}
        required_fields = [
            text_value(data, "customer_name"),
            text_value(data, "job_completed"),
            text_value(data, "contractor_name"),
            text_value(data, "company_name"),
            text_value(data, "contractor_phone", "phone_number"),
        ]
        if not all(required_fields):
            return jsonify({"error": "Please add the required referral-request details before generating."}), 400

        prompt = f"""
Write a referral request for a roofing contractor.
Return:
Email Version:
Text Message Version:

Customer first name: {text_value(data, "customer_name")}
Completed job: {text_value(data, "job_completed")}
Your name: {text_value(data, "contractor_name")}
Company name: {text_value(data, "company_name")}
Your phone: {text_value(data, "contractor_phone", "phone_number")}
Referral incentive: {text_value(data, "referral_incentive")}
Tone: {text_value(data, "tone") or "Professional"}

Keep it low-pressure, appreciative, and easy for the customer to forward.
"""
        result = generate_text(
            prompt,
            "You write referral request messages for roofing contractors. Keep them warm, concise, and respectful.",
        )
        log_generation(user["id"], "referral")
        return jsonify({"result": result, "tool": "referral"})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
