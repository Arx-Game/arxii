# Expectations for the round 3 check of item 15 (written before running)

Setup: major gift Pyrecraft works through the substance fire, whose property is fiery. Technique Kindle
of Pyrecraft stores two marks, fiery and smoky. The application "Light a pyre" needs fiery.

1. Technique admin change page for Kindle (staff user, real browser): shows a read-only field labelled
   "Property carried from its gift's substance" with the value "fiery" and the help line "Every technique
   of this gift carries it. It is not stored here and cannot be unticked."
2. In the page's stored-properties widget, remove fiery (leave smoky), press Save. Expect the success
   message. Reload: the stored widget lists smoky only, and the carried field still reads fiery.
   A shell read afterwards: stored marks = [smoky], has_property("fiery") = True, has_property("smoky") = True.
3. Power Builder page for "Light a pyre": Kindle's row shows fiery as a checked, disabled box with the
   words "carried from the gift's substance", and the footnote about a property a gift's substance gives.
   Save the Power Builder (nothing else changed): the page reloads with the same carried box, and a shell
   read shows has_property("fiery") still True for Kindle.
Nothing in these three steps may remove the carried property.
