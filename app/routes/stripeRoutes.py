import os
import stripe
import logging
from datetime import datetime
from bson import ObjectId
from flask import request, jsonify
from flask import redirect, render_template_string

# Logger
logger = logging.getLogger(__name__)

def setup_stripe_routes(app, mongo, cache):
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
    webhook_secret = os.getenv('WEBHOOK_SECRET')

    @app.route('/webhook', methods=['POST'])
    def stripe_webhook():
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            logger.error('Invalid payload')
            return jsonify({'error': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError:
            logger.error('Invalid signature')
            return jsonify({'error': 'Invalid signature'}), 400

        logger.info(f"Webhook recibido: {event['type']}")
        event_type = event['type']
        obj = event['data']['object']

        if event_type == 'checkout.session.completed':
            handle_checkout_session_completed(obj, mongo, cache)
        elif event_type == 'payment_intent.succeeded':
            handle_payment_intent_succeeded(obj, mongo, cache)
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(obj, mongo, cache)
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(obj, mongo, cache)
        elif event_type == 'invoice.paid':
            handle_invoice_paid(obj, mongo)

        logger.info(f"Evento procesado: {event_type}")
        return jsonify({'success': True}), 200

    @app.route('/create-checkout-session', methods=['POST'])
    def create_checkout_session():
        try:
            data = request.get_json()
            user_id = data.get('user_id')
            plan = data.get('plan')
            email = data.get('email')

            if not user_id or not ObjectId.is_valid(user_id):
                return jsonify({"error": "Valid user ID is required"}), 400
            if plan not in ['basic', 'premium', 'enterprise']:
                return jsonify({"error": "Valid plan is required"}), 400

            price_id = os.getenv(f'STRIPE_PRICE_{plan.upper()}')
            if not price_id:
                return jsonify({"error": "Stripe price not configured"}), 500

            checkout_session = stripe.checkout.Session.create(
                success_url=f"{request.host_url}payment/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{request.host_url}payment/cancel",
                payment_method_types=['card'],
                mode='subscription',
                customer_email=email,
                line_items=[{'price': price_id, 'quantity': 1}],
                metadata={'user_id': user_id, 'plan': plan}
            )

            mongo.database.payments.insert_one({
                'user_id': user_id,
                'stripe_session_id': checkout_session.id,
                'plan': plan,
                'status': 'pending',
                'created_at': datetime.utcnow()
            })

            return jsonify({"url": checkout_session.url})
        except Exception as e:
            logger.exception("Error creating checkout session")
            return jsonify({"error": str(e)}), 500

    @app.route('/change-subscription', methods=['POST'])
    def change_subscription():
        data = request.get_json() or {}
        user_id = data.get('user_id')
        new_plan = data.get('plan')

        if not (user_id and ObjectId.is_valid(user_id)):
            return jsonify(error="Valid user_id is required"), 400
        if new_plan not in ('basic', 'premium', 'enterprise'):
            return jsonify(error="Valid plan is required"), 400

        user = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify(error="User not found"), 404

        subscription_id = user.get('subscription', {}).get('stripe_subscription_id')
        if not subscription_id:
            return jsonify(error="No active subscription"), 400

        price_id = os.getenv(f'STRIPE_PRICE_{new_plan.upper()}')
        if not price_id:
            return jsonify(error="Pricing not configured"), 500

        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            updated_subscription = stripe.Subscription.modify(
                subscription_id,
                items=[{
                    'id': subscription['items']['data'][0]['id'],
                    'price': price_id,
                }],
                metadata={'user_id': user_id, 'plan': new_plan},
                proration_behavior='create_prorations'
            )

            mongo.database.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {
                    "subscription.plan": new_plan,
                    "subscription.active": True,
                    "subscription.updated_at": datetime.utcnow()
                }}
            )

            if user.get('correo'):
                cache.delete(user['correo'])

            current_period_end = updated_subscription.get('current_period_end')
            period_end_iso = datetime.fromtimestamp(current_period_end).isoformat() if current_period_end else None

            return jsonify(
                success=True,
                plan=new_plan,
                status=updated_subscription.status,
                current_period_end=period_end_iso
            )
        except Exception as e:
            logger.exception("Error changing subscription")
            return jsonify(error=str(e)), 500

    @app.route('/cancel-subscription', methods=['POST'])
    def cancel_subscription():
        data = request.get_json() or {}
        user_id = data.get('user_id')
        at_period_end = data.get('at_period_end', True)

        if not (user_id and ObjectId.is_valid(user_id)):
            return jsonify(error="Valid user_id is required"), 400

        user = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify(error="User not found"), 404

        subscription_id = user.get('subscription', {}).get('stripe_subscription_id')
        if not subscription_id:
            return jsonify(error="No active subscription"), 400

        try:
            canceled_subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=at_period_end
            )

            status_update = {
                "subscription.status": "scheduled_for_cancellation" if at_period_end else "canceled"
            }
            if not at_period_end:
                status_update["subscription.active"] = False
                status_update["subscription.canceled_at"] = datetime.utcnow()

            mongo.database.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": status_update}
            )

            if user.get('correo'):
                cache.delete(user['correo'])

            current_period_end = canceled_subscription.get('current_period_end')
            period_end_iso = datetime.fromtimestamp(current_period_end).isoformat() if current_period_end else None

            return jsonify(
                success=True,
                status=canceled_subscription.status,
                cancel_at_period_end=at_period_end,
                current_period_end=period_end_iso
            )
        except Exception as e:
            logger.exception("Error canceling subscription")
            return jsonify(error=str(e)), 500

    @app.route('/user-invoices', methods=['GET'])
    def user_invoices():
        user_id = request.args.get('user_id')

        if not (user_id and ObjectId.is_valid(user_id)):
            return jsonify(error="Valid user_id is required"), 400

        invoices = list(mongo.database.invoices.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1))

        for inv in invoices:
            if inv.get("paid_at"):
                inv["paid_at"] = inv["paid_at"].isoformat()
            if inv.get("created_at"):
                inv["created_at"] = inv["created_at"].isoformat()

        return jsonify(invoices=invoices), 200

    @app.route('/invoice-details', methods=['GET'])
    def invoice_details():
        invoice_id = request.args.get('invoice_id')

        if not invoice_id:
            return jsonify(error="Invoice ID is required"), 400

        try:
            invoice = stripe.Invoice.retrieve(invoice_id)
            items = [{
                "description": item.description,
                "amount": item.amount / 100,
                "currency": invoice.currency,
                "period_start": datetime.fromtimestamp(item.period.start).isoformat() if item.period else None,
                "period_end": datetime.fromtimestamp(item.period.end).isoformat() if item.period else None
            } for item in invoice.lines.data]

            invoice_data = {
                "invoice_id": invoice.id,
                "customer_id": invoice.customer,
                "status": invoice.status,
                "total": invoice.total / 100,
                "subtotal": invoice.subtotal / 100,
                "tax": (invoice.tax or 0) / 100,
                "currency": invoice.currency,
                "created": datetime.fromtimestamp(invoice.created).isoformat(),
                "due_date": datetime.fromtimestamp(invoice.due_date).isoformat() if invoice.due_date else None,
                "invoice_pdf": invoice.invoice_pdf,
                "hosted_invoice_url": invoice.hosted_invoice_url,
                "items": items
            }

            return jsonify(invoice=invoice_data), 200
        except Exception as e:
            logger.exception(f"Error retrieving invoice {invoice_id}")
            return jsonify(error=str(e)), 500

    @app.route('/payment/success', methods=['GET'])
    def payment_success():
        session_id = request.args.get('session_id')
        if not session_id:
            return "Missing session_id", 400

        try:
            # 1) Recuperar la sesión de Stripe
            session = stripe.checkout.Session.retrieve(session_id)
            customer = stripe.Customer.retrieve(session.customer)
            subscription_id = session.subscription

            # 2) Actualizar tu colección de pagos
            mongo.database.payments.update_one(
                {"stripe_session_id": session_id},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "stripe_subscription_id": subscription_id,
                    "customer_id": session.customer
                }},
                upsert=True
            )

            # 3) Actualizar usuario con la suscripción
            user_id = session.metadata.get('user_id')
            mongo.database.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {
                    "subscription.stripe_subscription_id": subscription_id,
                    "subscription.plan": session.metadata.get('plan'),
                    "subscription.active": True,
                    "subscription.start_date": datetime.utcnow(),
                    "subscription.status": "active"
                }}
            )
            # Limpiar cache si corresponde
            user = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
            if user.get('correo'):
                cache.delete(user['correo'])

            # 4) Mostrar mensaje de éxito o redirigir
            return render_template_string("""
                <h1>¡Pago exitoso!</h1>
                <p>Gracias por tu suscripción.</p>
            """)
        except Exception as e:
            logger.exception("Error in payment_success")
            return jsonify(error=str(e)), 500

    @app.route('/payment/cancel', methods=['GET'])
    def payment_cancel():
        return render_template_string("""
            <h1>Pago cancelado</h1>
            <p>Tu pago ha sido cancelado. Si fue un error, por favor intenta de nuevo.</p>
        """), 200


    # ─── Handlers ───────────────────────────────────────────────────────────────

    def handle_checkout_session_completed(session, mongo, cache):
        user_id = session.get('metadata', {}).get('user_id')
        if not user_id:
            return
        mongo.database.payments.update_one(
            {"stripe_session_id": session.id},
            {"$set": {"status": "completed", "completed_at": datetime.utcnow()}},
            upsert=True
        )

    def handle_payment_intent_succeeded(payment_intent, mongo, cache):
        logger.info(f"PaymentIntent succeeded: {payment_intent['id']}")

    def handle_subscription_updated(subscription, mongo, cache):
        # Ignora actualizaciones que marquen la suscripción como cancelada
        if subscription.get('status') == 'canceled':
            logger.warning(f"Ignorando suscripción cancelada: {subscription['id']}")
            return
        # Aquí tu lógica para actualizar la suscripción en MongoDB
        logger.info(f"Subscription updated: {subscription['id']}")

    def handle_subscription_deleted(subscription, mongo, cache):
        logger.info(f"Subscription deleted: {subscription['id']}")

    def handle_invoice_paid(invoice, mongo):
        logger.info(f"Invoice paid: {invoice['id']}")
        user_id = invoice.get("metadata", {}).get("user_id")
        if not user_id:
            logger.warning("Invoice missing user_id metadata")
            return
        mongo.database.invoices.insert_one({
            "user_id": user_id,
            "stripe_invoice_id": invoice.get("id"),
            "amount_paid": invoice.get("amount_paid") / 100,
            "status": invoice.get("status"),
            "invoice_pdf": invoice.get("invoice_pdf"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "paid_at": datetime.fromtimestamp(invoice.get("status_transitions", {}).get("paid_at", invoice["created"])),
            "created_at": datetime.fromtimestamp(invoice["created"]),
        })
