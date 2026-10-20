# Parcel Cart

R1. POST /estimate accepts JSON units (integer 1 through 9 inclusive), unit_cents (integer 1 through 10000 inclusive), and optional member (default false). subtotal is units multiplied by unit_cents, in integer cents.
R2. For a member, discounted is subtotal multiplied by 80 and integer-divided by 100 (round down). For a non-member discounted equals subtotal. delivery is 60 cents when discounted is below 500, otherwise zero. total equals discounted plus delivery.
R3. Zero, negative, fractional, string or out-of-range values for units or unit_cents are rejected with HTTP 422. Valid requests return HTTP 200 and the four fields subtotal, discounted, delivery and total.
