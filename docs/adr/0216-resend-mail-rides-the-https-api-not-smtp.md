# ADR-0216: Outbound mail rides Resend's HTTPS API, not SMTP

Context: production could not send any mail. Django's SMTP backend connected to
`smtp.resend.com:587`, and the host's upstream provider blocks outbound SMTP (587 and
465 both time out, to `smtp.resend.com` AND `smtp.gmail.com` alike) as a standard
outbound-SMTP policy outside our control. Because allauth sends a verification email
inline with account creation, the socket timeout surfaced as an HTTP 500 on the
signup endpoint, with an account already committed and no working delivery. Asking
the host to unblock SMTP was rejected: it is a blanket provider policy, not a
per-account setting we can flip, and it leaves a future move to a different host with
the identical outage. Port 443 to `api.resend.com` was already open and verified
working, and Resend already offers delivery over its own HTTPS API, so
`ResendAPIEmailBackend` (`world.roster.email_backend`) replaces the SMTP backend for
`EMAIL_BACKEND` in production, sending a short-timeout `POST
https://api.resend.com/emails` instead of opening an SMTP connection. This closes a
whole class of failure (provider-blocked outbound ports) rather than working around
one instance of it.

> Status: accepted · Source: production outage, signup 500s on every registration ·
> Related: none (no prior ADR recorded the SMTP transport choice)
