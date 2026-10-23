from pawabase_iac import P, Policy

mine = Policy("mine", P.owner("customer_id"), description="The signed-in customer owns the row.")
staff = Policy("staff", P.role("admin") | P.role("support"), description="Back-office users.")
staff_or_mine = Policy("staff_or_mine", P.role("admin") | P.role("support") | P.owner("customer_id"))
verified = Policy("verified", P.authenticated() & P.auth.email_verified.truthy())
big_spenders = Policy("big_spenders", P.authenticated() & (P.auth.lifetime_spend >= 1000) & ~P.auth.flagged.truthy())
