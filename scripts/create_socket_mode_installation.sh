#/bin/bash
if [ "$#" -ne 2 ]; then
    echo "Error: This script requires exactly two arguments."
    echo "Usage: $0 user_email slack_user_id"
    echo "Example: $0 email@example.com U12345ABCDE"
    exit 1
fi

source ~/envs/local.env
chmod +x ./dashboard/supercog/dashboard/slack/utils/create_socket_mode_installation.py                      
./dashboard/supercog/dashboard/slack/utils/create_socket_mode_installation.py $1 $2 --db-url=$DATABASE_URL
