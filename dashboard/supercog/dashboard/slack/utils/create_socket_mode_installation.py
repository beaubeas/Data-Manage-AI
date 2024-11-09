#!/usr/bin/env python3
import argparse
import os
import uuid
import time
from sqlalchemy import create_engine, text


def create_slack_installation(email: str, slack_user_id: str, db_url: str):
    """Create a slack installation record and link it to user"""

    # Replace the database name with monster_dashboard
    db_url_pieces = db_url.split("/")
    db_url_pieces[-1] = "monster_dashboard"

    # Create SQLAlchemy engine
    engine = create_engine("/".join(db_url_pieces))
    
    # Generate UUID and current timestamp
    installation_id = str(uuid.uuid4())
    installed_at = time.time()
    
    # SQL to insert slack installation
    insert_installation_sql = """
    INSERT INTO slack_installations (
        id, user_id, installed_at, is_enterprise_install
    ) VALUES (
        :id, :user_id, :installed_at, :is_enterprise_install
    )
    """
    
    # SQL to update user
    update_user_sql = """
    UPDATE users 
    SET slack_user_id = :slack_user_id
    WHERE email = :email
    """
    
    with engine.connect() as conn:
        # Insert slack installation
        conn.execute(
            text(insert_installation_sql),
            {
                "id": installation_id,
                "user_id": slack_user_id,
                "installed_at": installed_at,
                "is_enterprise_install": False
            }
        )
        
        # Update user record
        result = conn.execute(
            text(update_user_sql),
            {
                "slack_user_id": slack_user_id,
                "email": email
            }
        )
        
        if result.rowcount == 0:
            print(f"No user found with email {email}")
            return
            
        conn.commit()
        
        print(f"Successfully created slack installation {installation_id} for user {email}")

def main():
    parser = argparse.ArgumentParser(description='Create Slack installation record')
    parser.add_argument('email', help='User email')
    parser.add_argument('slack_user_id', help='Slack user ID')
    parser.add_argument('--db-url', help='Database URL',
                       default='postgresql://username:password@localhost:5432/monster_dashboard')
    
    args = parser.parse_args()
    
    try:
        create_slack_installation(args.email, args.slack_user_id, args.db_url)
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == '__main__':
    main()