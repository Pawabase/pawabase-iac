from infra.flows import low_stock, place_order, route_support, send_receipt

from pawabase_iac import Bucket, InboundHook, MailTemplate, P, Route, Schedule, Subscription, Webhook, env, every, variable

Route("/checkout", handler=place_order, method="POST", policy="authenticated")
Subscription("alert_on_low_stock", on="products.updated", run=low_stock)
Subscription("route_new_tickets", on="support.ticket.created", run=route_support)
Subscription("orders_feed", on="orders.created", publish_to="orders", condition=P.event.payload.record.total > 0)

Webhook("erp", url="https://erp.example.com/hooks/pawabase", events=["resource.orders.*", "stock.low"], secret=env("ERP_HOOK_SECRET"), max_attempts=8)
InboundHook("payments", run=place_order, verification="hmac-sha256", signature_header="x-payments-signature", secret=env("PAYMENTS_HOOK_SECRET"))

Schedule("expire_carts", event="carts.expire", interval=every(minutes=15), overlap="skip")
Schedule("daily_digest", run=send_receipt, cron="0 7 * * 1-5", timezone="Africa/Lagos", catch_up=True)

MailTemplate(
    "receipt",
    subject="Your receipt {{ order.id }}",
    html="<h1>Thanks!</h1><p>Total: {{ order.total }}</p>",
    text="Thanks! Total: {{ order.total }}",
    variables=[variable("order", "The order that was placed", {"id": "A-1042", "total": 49.5})],
    category="orders",
)

Bucket("product-images", public=True, accepts=["image/png", "image/jpeg", "image/webp"], max_bytes=5_000_000, write_policy="staff", cache_max_age=86400)
Bucket("invoices", public=False, signed_downloads=True, read_policy="staff_or_mine", write_policy="service", accepts=["application/pdf"])
