# Stripe Integration TODO

## What needs to be done
1. Create Stripe account at stripe.com
2. Create two products in Stripe dashboard:
   - Starter: $49/month recurring → copy the Price ID
   - Pro: $79/month recurring → copy the Price ID
3. Add these environment variables to Render:
   - STRIPE_SECRET_KEY
   - STRIPE_STARTER_PRICE_ID
   - STRIPE_PRO_PRICE_ID
   - YOUR_DOMAIN=https://roofdraft.com
4. Run the Stripe integration prompt in Claude Code

## Files that need updating when Stripe is added
Search the codebase for the comment: // STRIPE: and update each one

## Routes to add
- POST /api/stripe/create-checkout-session
- POST /api/stripe/webhook

## Webhook event to handle
- checkout.session.completed → update user plan in database
