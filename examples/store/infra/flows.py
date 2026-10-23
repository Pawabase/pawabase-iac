from infra.tables import orders, products

from pawabase_iac import Flow, P, blocks, ctx

# A route that places an order: validate, price the lines in a loop, charge, branch on the result, retry the notification.
place_order = Flow("place_order", description="Create an order from a cart and take payment", timeout=120)
start = place_order.add(blocks.trigger.http(method="POST", path="/checkout", policy="authenticated"))
user = place_order.add(blocks.auth.require(), id="signed_in")
valid = place_order.add(
    blocks.validate.schema(
        value=ctx.input,
        fields=[
            {"name": "items", "type": "array", "required": True},
            {"name": "coupon", "type": "string"},
        ],
    ),
    id="validate_cart",
)
bad_cart = place_order.add(blocks.error.raise_(status=422, message="That cart is not valid."), id="bad_cart")
lines = place_order.add(blocks.control.foreach(items=ctx.input.items, concurrency=1), id="each_line")
price = place_order.add(blocks.resource.get(resource=products, id=ctx.item.sku), id="load_product")
missing = place_order.add(blocks.error.raise_(status=404, message=ctx.text("No such product: ", ctx.item.sku)), id="no_product")
total = place_order.add(blocks.transform.summarize(value=ctx.vars.lines, operation="sum", field="amount"), id="total")
is_big = place_order.add(blocks.control.if_(P.steps.total.output > 1000), id="is_big")
review = place_order.add(blocks.event.emit(event="orders.needs_review", payload={"total": ctx.steps.total.output}), id="flag_for_review")
create = place_order.add(
    blocks.resource.create(resource=orders, data={"customer_id": ctx.auth.user_id, "total": ctx.steps.total.output, "status": "new"}),
    id="create_order",
)
charge = place_order.add(
    blocks.http.request(
        method="POST", url="https://payments.example.com/charge", body={"amount": ctx.steps.total.output, "order": ctx.steps.create_order.output.id},
        timeout=20, retries=3,
    ),
    id="charge",
)
paid = place_order.add(blocks.resource.update(resource=orders, id=ctx.steps.create_order.output.id, data={"status": "paid"}), id="mark_paid")
declined = place_order.add(blocks.resource.update(resource=orders, id=ctx.steps.create_order.output.id, data={"status": "new"}), id="mark_declined")
fail = place_order.add(blocks.error.raise_(status=402, message="Payment failed.", code="payment_failed"), id="payment_failed")
notify = place_order.add(blocks.queue.flow(flow="send_receipt", input={"order_id": ctx.steps.create_order.output.id}, delay=5), id="queue_receipt")
done = place_order.add(blocks.response.return_(status=201, body={"order": ctx.steps.create_order.output}), id="done")

start >> user >> valid
valid.invalid >> bad_cart
valid >> lines
lines.each >> price
price.missing >> missing
lines.done >> total >> is_big
is_big.true >> review >> create
is_big.false >> create
create >> charge
charge >> paid >> notify >> done
charge.failed >> declined >> fail

# A receipt flow, queued by the one above and also callable by hand.
send_receipt = Flow("send_receipt", description="Email the receipt for an order")
send_receipt.chain(
    blocks.trigger.job(queue="default"),
    blocks.resource.get(resource=orders, id=ctx.input.order_id),
    blocks.mail.send(to=ctx.steps.resource_get.output.email, template="receipt", data={"order": ctx.steps.resource_get.output}),
)

# Reacting to a change in a table.
low_stock = Flow("low_stock_alert", description="Tell staff when stock falls below five")
low_stock.chain(
    blocks.trigger.resource(resource=products, operations=["update"]),
    blocks.control.if_(P.input.record.stock < 5),
)
low_stock.nodes["control_if"].true >> low_stock.add(blocks.webhook.send(event="stock.low", payload={"sku": ctx.input.record.sku}))
low_stock.nodes["control_if"].true >> low_stock.add(blocks.realtime.publish(channel="staff", event="stock.low", payload={"sku": ctx.input.record.sku}))

# Fan-out with a switch and a retry wrapper.
route_support = Flow("route_ticket", description="Send a support ticket to the right queue")
t = route_support.add(blocks.trigger.event(event="support.ticket.created"))
sw = route_support.add(blocks.control.switch(value=ctx.input.category, cases=["billing", "technical", "other"]), id="by_category")
t >> sw
sw.on("billing") >> blocks.queue.flow(flow="billing_desk", input=ctx.input)
sw.on("technical") >> blocks.queue.flow(flow="tech_desk", input=ctx.input)
sw.on("default") >> blocks.log.write(message=ctx.text("uncategorised ticket ", ctx.input.id), level="warning")

for desk, message in (("billing_desk", "billing ticket"), ("tech_desk", "technical ticket")):
    Flow(desk, description=f"Handle a {message}").chain(
        blocks.trigger.job(queue="support"),
        blocks.log.write(message=ctx.text(message, " ", ctx.input.id), level="info"),
        blocks.mail.send(to="support@example.com", subject=ctx.text("New ", message), text=ctx.input.body),
    )
