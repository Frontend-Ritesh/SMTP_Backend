#!/bin/sh
set -e
sed -i "s|__SQL_RO_USER__|${SQL_RO_USER}|; s|__SQL_RO_PASSWORD__|${SQL_RO_PASSWORD}|; s|__POSTGRES_DB__|${POSTGRES_DB}|" \
    /etc/dovecot/dovecot-sql.conf.ext
# Master user password file (webmail service credential).
printf '%s:{ARGON2ID}%s\n' "${DOVECOT_MASTER_USER}" \
  "$(doveadm pw -s ARGON2ID -p "${DOVECOT_MASTER_PASSWORD}" | sed 's/{ARGON2ID}//')" \
  > /etc/dovecot/master-users
chown dovecot:dovecot /etc/dovecot/master-users
chmod 600 /etc/dovecot/master-users

# Generate EC keypair for mail-crypt if not exists
if [ ! -f /var/vmail/ecprivkey.pem ]; then
  echo "Generating mail-crypt key pair..."
  openssl ecparam -name prime256v1 -genkey -noout -out /var/vmail/ecprivkey.pem
  openssl ec -in /var/vmail/ecprivkey.pem -pubout -out /var/vmail/ecpubkey.pem
  chown vmail:vmail /var/vmail/ecprivkey.pem /var/vmail/ecpubkey.pem
  chmod 600 /var/vmail/ecprivkey.pem
  chmod 644 /var/vmail/ecpubkey.pem
fi

exec dovecot -F
