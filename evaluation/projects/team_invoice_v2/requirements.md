# Team Invoice

R1. Seats must be an integer from 1 through 8 inclusive. Basic costs 120 cents per seat; Pro costs 200 cents per seat. A monthly quote is seats times the plan price plus a fixed 30-cent processing fee. A valid Quote with Terms checked displays that integer total and notice Ready.
R2. Annual quotes discount the base seat cost by 25 percent, rounding down to integer cents, then add the full 30-cent processing fee. The fee is not discounted.
R3. Initially Seats is 2, Plan is Basic, Annual and Terms are unchecked, quote displays — and notice is empty. Quote with Terms unchecked displays Accept terms and does not change the existing quote, including a quote produced by an earlier successful calculation.
R4. Zero, negative, fractional or above-8 Seats displays Seats must be an integer from 1 to 8 and preserves the existing quote. This validation takes precedence over the Terms check.
