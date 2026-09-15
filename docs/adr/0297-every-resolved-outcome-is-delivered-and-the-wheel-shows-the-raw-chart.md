# Every resolved outcome is delivered, and the wheel shows the raw chart

Three decisions from #3807, each hard to reverse once code depends on the shape.

**1. Every resolved outcome row is delivered live, on web and telnet, to the row's
own audience, after the writing transaction commits.** Delivery is not a per-feature
design question: three writers persisted a social-check result, a treatment
outcome, and a cast outcome pose without ever pushing them to a client, and the
issue that caught it was filed asking whether to show the outcome at all. Rejected
alternative: treating "should this be delivered" as an open design call per
feature, the framing the filing itself used. A player always sees what their own
action did; only the audience is ever a real question.

**2. A social check spins a success-level wheel for the roller and the target (roller
only when there is no target), sized by the real chart bands the check was rolled
against.** Rejected alternatives: equal-sized slices for every face (reads as
theater with no relationship to the actual odds), and showing the wheel to
bystanders (the roll belongs to the people it happened to, not the room).

**3. The wheel never reflects rollmod or an outcome guarantee.** It is built from
the raw chart and lands on the already-resolved outcome; when a guarantee lifted
that outcome off the chart entirely, a thin slice is appended so the wheel still
has a face to land on, rather than silently reshaping the real bands. Rejected
alternative: showing the effective odds (after rollmod and guarantees), which
would leak a secret staff lever to the player it was used on.

> Status: accepted · Source: #3807
