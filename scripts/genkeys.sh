#/bin/bash
echo "Run this script from the scbeta root directory"
mkdir ./dashboard/keys
openssl ecparam -name prime256v1 -genkey -noout -out ./dashboard/keys/dash_ecdsa_private_key.pem
openssl ec -in ./dashboard/keys/dash_ecdsa_private_key.pem -pubout -out ./dashboard/keys/dash_ecdsa_public_key.pem
export DASH_PRIVATE_KEY=$(base64 < "./dashboard/keys/dash_ecdsa_private_key.pem" | tr -d '\n')
export DASH_PUBLIC_KEY=$(base64 < "./dashboard/keys/dash_ecdsa_public_key.pem" | tr -d '\n')
echo "DASH_PRIVATE_KEY=$DASH_PRIVATE_KEY"
echo "DASH_PUBLIC_KEY=$DASH_PUBLIC_KEY"
