def payment_webhook_received(payment, obj):
    payment.status = obj['status']
    payment.save()
