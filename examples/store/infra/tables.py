from infra.policies import big_spenders, mine, staff, staff_or_mine, verified

from pawabase_iac import (
    Allow, Array, BelongsTo, Boolean, Desc, Email, HasMany, Index, Integer, Number, Object, RateLimit, Ref, Schema, String, Table, Text,
    Transformer, Where, crud, read_only,
)

address = Schema("Address", fields=[String("line1", required=True), String("city", required=True), String("postcode", pattern=r"^[A-Z0-9 ]{3,10}$")])
public_product = Transformer("public_product", omit=["cost_price", "supplier"], case="camel")

customers = Table(
    "customers",
    fields=[
        String("customer_id", required=True, unique=True),
        String("name", required=True, max_length=120),
        Email("email", required=True, unique=True),
        Ref("billing_address", schema=address),
        Array("tags", of=String("tag", max_length=30)),
        Integer("loyalty_points", minimum=0, default=0),
    ],
    operations=crud(staff_or_mine, create=Allow(verified), delete=Allow(staff)),
    owner_field="customer_id",
    indexes=[Index("email", unique=True, name="uniq_customer_email")],
    rate_limit=RateLimit(60, 60),
)

products = Table(
    "products",
    fields=[
        String("sku", required=True, unique=True),
        String("title", required=True, max_length=200),
        Text("description"),
        Number("price", required=True, minimum=0),
        Number("cost_price", minimum=0),
        String("supplier"),
        Integer("stock", minimum=0, default=0),
        Boolean("active", default=True),
        String("status", enum=["draft", "live", "retired"], default="draft"),
    ],
    operations={**read_only("public"), "create": Allow(staff), "update": Allow(staff), "delete": Allow(staff)},
    transformer=public_product,
    cache_ttl=60,
    indexes=[Index("status", Desc("price"), where=[Where("active", "=", True)])],
    realtime=True,
)

orders = Table(
    "orders",
    fields=[
        String("customer_id", required=True),
        Number("total", required=True, minimum=0),
        String("status", enum=["new", "paid", "shipped", "refunded"], default="new"),
        Object("shipping", fields=[String("line1"), String("city")]),
    ],
    operations=crud(staff_or_mine, delete=Allow(staff)),
    owner_field="customer_id",
    relations=[BelongsTo("customer", customers, "customer_id"), HasMany("items", "order_items", "order_id")],
    indexes=[Index("customer_id", Desc("created_at")), Index("status", where=[Where("status", "!=", "refunded")], name="live_orders")],
    events=True,
    capture=False,
)

order_items = Table(
    "order_items",
    fields=[String("order_id", required=True), String("sku", required=True), Integer("qty", required=True, minimum=1, maximum=100), Number("unit_price", required=True)],
    operations=crud(staff),
    relations=[BelongsTo("order", orders, "order_id")],
    indexes=[Index("order_id")],
)

vip_offers = Table("vip_offers", fields=[String("title", required=True)], operations=read_only(big_spenders))
