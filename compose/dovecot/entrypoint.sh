#!/bin/sh
set -e
sed -i "s|__SQL_RO_USER__|${SQL_RO_USER}|; s|__SQL_RO_PASSWORD__|${SQL_RO_PASSWORD}|; s|__POSTGRES_DB__|${POSTGRES_DB}|" \
    /etc/dovecot/dovecot-sql.conf.ext
# Generate EC keypair for mail-crypt if not exists
if [ ! -f /var/vmail/ecprivkey.pem ]; then
  echo "Generating mail-crypt key pair..."
  openssl ecparam -name prime256v1 -genkey -noout -out /var/vmail/ecprivkey.pem
  # Convert to traditional format (SEC1) required by Dovecot mail_crypt
  openssl ec -in /var/vmail/ecprivkey.pem -out /var/vmail/ecprivkey.pem
  chown vmail:vmail /var/vmail/ecprivkey.pem
  chmod 600 /var/vmail/ecprivkey.pem
fi

if [ ! -f /var/vmail/ecpubkey.pem ]; then
  echo "Generating mail-crypt public key..."
  openssl ec -in /var/vmail/ecprivkey.pem -pubout -out /var/vmail/ecpubkey.pem
  chown vmail:vmail /var/vmail/ecpubkey.pem
  chmod 644 /var/vmail/ecpubkey.pem
fi

# Master user password file (webmail service credential).
printf '%s:{ARGON2ID}%s\n' "${DOVECOT_MASTER_USER}" \
  "$(doveadm pw -s ARGON2ID -p "${DOVECOT_MASTER_PASSWORD}" | sed 's/{ARGON2ID}//')" \
  > /etc/dovecot/master-users
chown dovecot:dovecot /etc/dovecot/master-users
chmod 600 /etc/dovecot/master-users

# Dynamically set SSL certificate paths based on MAIL_HOSTNAME
if [ -n "${MAIL_HOSTNAME}" ]; then
  sed -i "s|/etc/letsencrypt/live/mail.polynexus.in/|/etc/letsencrypt/live/${MAIL_HOSTNAME}/|g" /etc/dovecot/dovecot.conf
fi

exec dovecot -F
