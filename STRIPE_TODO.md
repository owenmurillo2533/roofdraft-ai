# Stripe Launch Checklist

## What still needs to happen in Stripe
1. Revoke any previously exposed secret key and generate a fresh live `STRIPE_SECRET_KEY`.
2. In live mode, create the public Pro product:
   - Pro: $79/month recurring -> copy the Price ID into `STRIPE_PRO_PRICE_ID`
3. Add these environment variables in Render:
   - `STRIPE_SECRET_KEY`
   - `STRIPE_PRO_PRICE_ID`
   - `STRIPE_WEBHOOK_SECRET`
   - `YOUR_DOMAIN=https://roofdraftai.com`
4. Create a webhook endpoint in Stripe for:
   - `https://roofdraftai.com/api/stripe/webhook`
   - event: `checkout.session.completed`
5. Run one real end-to-end purchase test in live mode with your own card, then cancel it.

## Legacy Starter plan
- Public checkout is now Pro-only.
- If legacy Starter billing ever needs to be reopened for existing users, set:
  - `ENABLE_LEGACY_STARTER_CHECKOUT=true`
  - `STRIPE_STARTER_PRICE_ID=<legacy starter price id>`

## Current routes in code
- `POST /api/stripe/create-checkout-session`
- `POST /api/stripe/webhook`
