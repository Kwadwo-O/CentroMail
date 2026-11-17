"""Address syntax and cached DNS checks; these do not prove mailbox ownership."""
from email_validator import (
    EmailSyntaxError, EmailUndeliverableError, caching_resolver, validate_email,
)

resolver = caching_resolver(timeout=3)


def email_address_error(address, *, check_domain=False):
    try:
        result = validate_email(address, check_deliverability=check_domain,
                                allow_smtputf8=False, strict=True, dns_resolver=resolver)
    except EmailSyntaxError:
        return "Enter a valid email address."
    except EmailUndeliverableError:
        return "This email domain does not exist or cannot receive email. Check the address."
    if check_domain and not getattr(result, 'mx', None):
        return "The email domain could not be checked right now. Please try again."
    return ""
