# mail/admin.py
# MessageMeta is intentionally NOT registered in Django admin.
# Registering it would allow staff to browse client email subject lines,
# sender addresses and snippets — a serious client privacy violation.
# The mail index exists only to power the webmail UI for the mailbox owner.
