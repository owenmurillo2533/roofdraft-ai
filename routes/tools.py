"""
RoofDraft AI — Tools Routes
"""
import os
from flask import Blueprint, request, jsonify
from anthropic import Anthropic
from database.db import require_auth, log_generation, get_monthly_count, save_draft, USE_POSTGRES, pg_run

tools_bp = Blueprint('tools', __name__)

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2000

# ---------------------------------------------------------------------------
# Plan enforcement
# ---------------------------------------------------------------------------

TOOL_ACCESS = {
    'free':    ['proposal'],
    'starter': ['proposal'],
    'pro':     ['proposal', 'followup', 'review', 'referral'],
    'admin':   ['proposal', 'followup', 'review', 'referral'],
}

FREE_LIMIT = 5
PAYING_PLANS = {'starter', 'pro'}


def is_paying(user):
    return bool(user.get('is_admin')) or user.get('plan', 'free') in PAYING_PLANS


def check_access(user, tool_name):
    """Returns (allowed: bool, error_message: str | None)."""
    plan = user.get('plan', 'free')
    is_admin = bool(user.get('is_admin', False))

    if is_admin:
        return True, None

    allowed_tools = TOOL_ACCESS.get(plan, ['proposal'])
    if tool_name not in allowed_tools:
        return False, "This tool requires a Pro plan. Upgrade to access all 4 tools."

    if plan == 'free':
        count = get_monthly_count(user['id'])
        if count >= FREE_LIMIT:
            return False, "You've used all your free generations this month. Upgrade to continue."

    return True, None


def auth_and_check(tool_name):
    """Authenticate request and check plan access. Returns (user, error_response)."""
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    allowed, msg = check_access(user, tool_name)
    if not allowed:
        return None, (jsonify({"error": msg}), 403)

    return user, None


# ---------------------------------------------------------------------------
# Tool: Proposal Generator
# ---------------------------------------------------------------------------

@tools_bp.route('/api/tools/proposal', methods=['POST'])
def proposal():
    user, err = auth_and_check('proposal')
    if err:
        return err

    data = request.get_json() or {}

    customer_name     = data.get('customer_name', '')
    customer_address  = data.get('customer_address', '')
    roof_type         = data.get('roof_type', '')
    square_footage    = data.get('square_footage', '')
    pitch             = data.get('pitch', '')
    materials         = data.get('materials', '')
    scope             = data.get('scope', '')
    price_total       = data.get('price_total', '')
    deposit_required  = data.get('deposit_required', '')
    payment_terms     = data.get('payment_terms', '')
    warranty_labor    = data.get('warranty_labor', '')
    warranty_materials = data.get('warranty_materials', '')
    company_name      = data.get('company_name', '')
    contractor_name   = data.get('contractor_name', '')
    contractor_phone  = data.get('contractor_phone', '')
    contractor_email  = data.get('contractor_email', '')
    license_number    = data.get('license_number', '')
    start_date        = data.get('start_date', '')
    completion_days   = data.get('completion_days', '')

    user_prompt = f"""Using the inputs provided, write a complete, professional roofing proposal letter formatted for a homeowner or property owner.

TONE: Confident and professional, not salesy. Clear and easy for a homeowner to understand. Warm but businesslike.

FORMAT:
- Start with a professional header block (company name, contractor name, contact info, date, proposal number — generate a random proposal number like RD-XXXX)
- Include a Prepared For section with customer name and address
- Write the scope of work in clear prose paragraphs, not bullet points
- Include a materials section
- Include a pricing section with a clean breakdown (total, deposit, remaining balance)
- Include warranty information
- Include payment terms
- Close with a professional paragraph that builds confidence
- End with a signature block with space for customer signature and date
- Add: This proposal is valid for 30 days

DO NOT use filler phrases like we are pleased to offer. DO NOT use bullet points in the main body. DO NOT include placeholder brackets.

INPUTS:
Customer Name: {customer_name}
Property Address: {customer_address}
Roof Type: {roof_type}
Square Footage: {square_footage} sq ft
Roof Pitch: {pitch}
Materials: {materials}
Scope of Work: {scope}
Total Price: ${price_total}
Deposit Required: ${deposit_required}
Payment Terms: {payment_terms}
Labor Warranty: {warranty_labor}
Materials Warranty: {warranty_materials}
Company Name: {company_name}
Contractor Name: {contractor_name}
Phone: {contractor_phone}
Email: {contractor_email}
License Number: {license_number}
Estimated Start Date: {start_date}
Estimated Completion: {completion_days} business days"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You are a professional proposal writer for a residential and commercial roofing company. Your job is to write polished, trust-building roofing proposals that help contractors win more jobs.",
            messages=[{"role": "user", "content": user_prompt}]
        )
        result = message.content[0].text
        log_generation(user['id'], 'proposal')
        draft_id = None
        if is_paying(user):
            title = f"Proposal — {customer_name}" + (f", {customer_address}" if customer_address else "")
            draft_id = save_draft(user['id'], 'proposal', title[:255], result)
        return jsonify({"result": result, "tool": "proposal", "draft_id": draft_id})
    except Exception as e:
        print(f"[Tools/proposal] Error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Generation failed — please try again"}), 500


# ---------------------------------------------------------------------------
# Tool: Follow-Up Email
# ---------------------------------------------------------------------------

@tools_bp.route('/api/tools/followup', methods=['POST'])
def followup():
    user, err = auth_and_check('followup')
    if err:
        return err

    data = request.get_json() or {}

    customer_name      = data.get('customer_name', '')
    days_since_proposal = data.get('days_since_proposal', '')
    proposal_amount    = data.get('proposal_amount', '')
    job_type           = data.get('job_type', '')
    contractor_name    = data.get('contractor_name', '')
    company_name       = data.get('company_name', '')
    contractor_phone   = data.get('contractor_phone', '')

    user_prompt = f"""Write 3 follow-up email variations for a roofing contractor who sent a proposal {days_since_proposal} days ago and hasn't heard back.

RULES: Under 120 words each. No just checking in. No pressure tactics. One soft call to action. Sound like a real human. Include subject line for each.

Label them Option A, Option B, Option C.

INPUTS:
Customer Name: {customer_name}
Days Since Proposal: {days_since_proposal}
Proposal Amount: ${proposal_amount}
Job Type: {job_type}
Contractor Name: {contractor_name}
Company: {company_name}
Phone: {contractor_phone}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You are a professional copywriter who writes follow-up emails for roofing contractors.",
            messages=[{"role": "user", "content": user_prompt}]
        )
        result = message.content[0].text
        log_generation(user['id'], 'followup')
        draft_id = None
        if is_paying(user):
            title = f"Follow-Up — {customer_name}" + (f" ({job_type})" if job_type else "")
            draft_id = save_draft(user['id'], 'followup', title[:255], result)
        return jsonify({"result": result, "tool": "followup", "draft_id": draft_id})
    except Exception as e:
        print(f"[Tools/followup] Error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Generation failed — please try again"}), 500


# ---------------------------------------------------------------------------
# Tool: Review Request
# ---------------------------------------------------------------------------

@tools_bp.route('/api/tools/review', methods=['POST'])
def review():
    user, err = auth_and_check('review')
    if err:
        return err

    data = request.get_json() or {}

    customer_name   = data.get('customer_name', '')
    job_type        = data.get('job_type', '')
    contractor_name = data.get('contractor_name', '')
    company_name    = data.get('company_name', '')
    review_link     = data.get('review_link', '')

    user_prompt = f"""Write a text message version and an email version of a Google review request.

RULES: Text under 160 characters. Email under 80 words with subject line. Both sound personal and human, not corporate. Do not say if you have a moment. Do not offer incentives.

INPUTS:
Customer First Name: {customer_name}
Job Type: {job_type}
Contractor Name: {contractor_name}
Company: {company_name}
Google Review Link: {review_link}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You write Google review request messages for roofing contractors.",
            messages=[{"role": "user", "content": user_prompt}]
        )
        result = message.content[0].text
        log_generation(user['id'], 'review')
        draft_id = None
        if is_paying(user):
            title = f"Review Request — {customer_name}" + (f" ({job_type})" if job_type else "")
            draft_id = save_draft(user['id'], 'review', title[:255], result)
        return jsonify({"result": result, "tool": "review", "draft_id": draft_id})
    except Exception as e:
        print(f"[Tools/review] Error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Generation failed — please try again"}), 500


# ---------------------------------------------------------------------------
# Tool: Referral Message
# ---------------------------------------------------------------------------

@tools_bp.route('/api/tools/referral', methods=['POST'])
def referral():
    user, err = auth_and_check('referral')
    if err:
        return err

    data = request.get_json() or {}

    customer_name      = data.get('customer_name', '')
    job_completed      = data.get('job_completed', '')
    contractor_name    = data.get('contractor_name', '')
    company_name       = data.get('company_name', '')
    referral_incentive = data.get('referral_incentive', '')
    phone_number       = data.get('phone_number', '')

    user_prompt = f"""Write a text message version and an email version of a referral request.

RULES: Natural conversation tone. Not awkward or salesy. If referral_incentive is provided mention it naturally do not lead with it. If blank do not mention incentives. Clear easy next step at the end.

INPUTS:
Customer First Name: {customer_name}
Job Completed: {job_completed}
Contractor Name: {contractor_name}
Company: {company_name}
Referral Incentive: {referral_incentive}
Phone: {phone_number}"""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You write referral request messages for roofing contractors.",
            messages=[{"role": "user", "content": user_prompt}]
        )
        result = message.content[0].text
        log_generation(user['id'], 'referral')
        draft_id = None
        if is_paying(user):
            title = f"Referral — {customer_name}" + (f" ({job_completed})" if job_completed else "")
            draft_id = save_draft(user['id'], 'referral', title[:255], result)
        return jsonify({"result": result, "tool": "referral", "draft_id": draft_id})
    except Exception as e:
        print(f"[Tools/referral] Error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Generation failed — please try again"}), 500
