import asyncio
import json
import sys
import traceback
import requests
import rollbar
import time

from typing import AsyncGenerator
from uuid import uuid4
import reflex as rx
from sqlmodel import select, or_, Session

from supercog.shared.apubsub import pubsub
from supercog.shared.oauth_utils import google_refresh_token
from supercog.shared.utils import send_email, EMAIL_KEYS
from supercog.shared.logging import logger
from supercog.shared.services import config

from .models import User, Tenant, TenantMember, Folder
from .global_state import GlobalState

from collections.abc import AsyncGenerator

# Google auth
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport import requests as gauth_requests
from requests_oauthlib import OAuth2Session

GOOGLE_CLIENT_ID = config.get_global("GOOGLE_CLIENT_ID", required=False) or "skip"
GOOGLE_CLIENT_SECRET = config.get_global("GOOGLE_CLIENT_SECRET", required=False)
SKIP_EMAIL_VERIFICATION = bool(config.get_global("SKIP_EMAIL_VERIFICATION", required=False))

class LoginState(GlobalState):
    # Traditional LoginRegState class

    # State handler for registration and login pages.

    reg_success: bool = False
    reg_error_message: str = ""

    def on_page_load(self):
        self.reg_error_message = ""
        self.reg_success = False
        
    async def register_page_load(self) -> str|None:
        secret = self.router.page.params.get("secret", "")
        if secret:
            self.reg_success = True
            return await self.handle_email_confirm(secret)

    # Handle email registration form submission. We create the User record but set it as enabled=False
    # until the user confirms they own the email address. We do this by sending an email with a link
    # that contains a secret key. When the user clicks the link, we look up the secret key in Redis
    # and if it matches, we enable the user account and log them in.
    async def handle_registration(
        self, form_data
    ) -> AsyncGenerator[rx.event.EventSpec | list[rx.event.EventSpec] | None, None]:
        """Handle registration form on_submit.

        Set reg_error_message appropriately based on validation results.

        Args:
            form_data: A dict of form fields and values.
        """
        with rx.session() as session:
            name = form_data["name"]
            email = form_data["email"]
            if not name:
                self.reg_error_message = "Name cannot be empty"
                yield rx.set_focus("name")
                return
            existing_user = session.exec(
                select(User).where(or_(User.email == email, User.gtoken_email == email))
            ).one_or_none()
            if existing_user is not None:
                self.reg_error_message = (
                    f"Email {email} is already registered. Try a different email or use Google auth."
                )
                yield [rx.set_value("email", ""), rx.set_focus("email")]
                return
            password = form_data["password"]
            if not password:
                self.reg_error_message = "Password cannot be empty"
                yield rx.set_focus("password")
                return
            if password != form_data["confirm_password"]:
                self.reg_error_message = "Passwords do not match"
                yield [
                    rx.set_value("confirm_password", ""),
                    rx.set_focus("confirm_password"),
                ]
                return
            # Create the new (disabled) user and add it to the database.
            user = self.create_user_from_email(
                session, 
                name, 
                email, 
                password, 
                enabled=SKIP_EMAIL_VERIFICATION,
            )

            session.add(user)
            session.commit()
            session.refresh(user)
            self.resolve_new_user_tenant(user, session)        

            # Now send the user a confirmation email
            if SKIP_EMAIL_VERIFICATION:
                self._login(user.id, user.name or "")
                yield [LoginState.redir(), LoginState.finish_user_create(user.id)]
            else:
                self.reg_error_message = ""
                self.reg_success = True
                secret = "confirm:" + uuid4().hex
                await pubsub.set(secret, user.id, ttl=60*60)
                link = f"{self.get_server_host}?secret={secret}"
                send_email(user.email, EMAIL_KEYS.EMAIL_CONFIRM, {"link":link})

    # When the user clicks the confirm link they come back here. We enable their account and log them in.
    async def handle_email_confirm(self, secret):
        signup_key = await pubsub.get(secret)

        if signup_key is None:
            self.reg_error_message = "Link expired"
            return None
        else:
            await pubsub.delete(secret)
            user_id = signup_key
            with rx.session() as sess:
                user = sess.get(User, user_id)
                if user:
                    user.enabled = True
                    sess.commit()
                    sess.refresh(user)
                    self._login(user.id, user.name or "")
                return [LoginState.redir(), LoginState.finish_user_create(user.id)]


    # Success callback after a Google login. Exchanges code for Oauth tokens and fetches user info.
    async def on_google_auth(self, code: dict):
        try:
            google = OAuth2Session(GOOGLE_CLIENT_ID, redirect_uri=self.router.page.host)
            tokens = google.fetch_token(
                code=code['code'], 
                token_url="https://www.googleapis.com/oauth2/v4/token", 
                client_secret=GOOGLE_CLIENT_SECRET,
            )
            # Need to save tokens in the User record
            # Now get the user info
            google_user_info = verify_oauth2_token(
                tokens['id_token'],
                gauth_requests.Request(),
                GOOGLE_CLIENT_ID,
            )
            # Link to account with existing email, or create a new User
            with rx.session() as session:
                user = session.exec(select(User).where(User.gtoken_sub == google_user_info["sub"])).first()
                if user is None:
                    # No existing Google user, look for email match
                    user = session.exec(select(User).where(User.email == google_user_info["email"])).first()
                    if user:
                        # This is merging the Google login into an existing email user
                        self.update_user_from_google(user, google_user_info)
                        session.add(user)
                        session.commit()
                        session.refresh(user)
                if user is None:
                    # No existing user, create a new one
                    user = self.create_user_from_google(google_user_info)
                    session.add(user)
                    session.commit()
                    session.refresh(user)
                    self.resolve_new_user_tenant(user, session)        
                    yield LoginState.finish_user_create(user.id)
                if user and user.id:
                    self._login(user.id, user.name or "")
                self.reg_error_message = ""
                yield LoginState.redir()       # type: ignore             
        except:
            rollbar.report_exc_info(sys.exc_info(), extra_data={"code": code})
            traceback.print_exc()
            self.reg_error_message = "There was a problem logging in, please try again."


    # Don't think we actually need this. This would let us refresh our google token out of band
    # but we really only go back to Google after a new login anyway...
    def _refresh_google_token(self, sess, user):
        tokens = json.loads(user.gtoken_json)
        if 'expires_at' in tokens and int(tokens['expires_at']) < time.time():
            print("Refreshing Google Access token")
            new_toks = google_refresh_token({
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": tokens['refresh_token'],
            })
            if 'access_token' in new_toks:
                tokens['access_token'] = new_toks['access_token']
                tokens['expires_at'] = time.time() + new_toks['expires_in']
                user.gtoken_json = json.dumps(tokens)
                sess.add(user)
                sess.commit()
                sess.refresh(user)


    def on_submit_email_login(self, form_data) -> rx.event.EventSpec:
        """Handle login form on_submit.

        Args:
            form_data: A dict of form fields and values.
        """
        self.reg_error_message = ""
        email = form_data["email"]
        password = form_data["password"]
        with rx.session() as session:
            user = session.exec(
                select(User).where(User.email == email)
            ).one_or_none()
        if user is not None and not user.enabled:
            self.reg_error_message = "This account is disabled."
            return rx.set_value("password", "")
        if user is None or not user.verify(password):
            self.reg_error_message = "There was a problem logging in, please try again."
            return rx.set_value("password", "")
        if (
            user is not None
            and user.id is not None
            and user.enabled
            and user.verify(password)
        ):
            # mark the user as logged in
            self._login(user.id, user.name or "")
        self.reg_error_message = ""
        return LoginState.redir() # type: ignore

    ########################################
    # Supercog specific login methods
    ########################################

    pwreset_email: str = ""
    pwreset_message: str = ""
    pwreset_secret: str = ""

    def create_user_from_email(self, session, username, email, password, enabled=True) -> User:
        new_user = User(tenant_id="notset")  # type: ignore
        new_user.name = username
        new_user.email = email
        new_user.enabled = enabled
        new_user.password_hash = User.hash_password(password)
        return new_user

    def update_user_from_google(self, user: User, google_user_info: dict):
        user.gtoken_sub=google_user_info["sub"],
        user.gtoken_email=google_user_info["email"],
        user.gtoken_info_json=json.dumps(google_user_info),
        user.gtoken_json="",

    def create_user_from_google(self, google_user_info: dict):
        # No existing user, create a new one
        return User(
            gtoken_sub=google_user_info["sub"],
            gtoken_email=google_user_info["email"],
            gtoken_info_json=json.dumps(google_user_info),
            gtoken_json="",
            tenant_id="notset",
            email=google_user_info["email"],
            name=google_user_info["name"],
            password_hash=None,
            enabled=True,
            created_at=None,
        ) 

    # Declan - I think we should put most of the User setup code in here. Or refactor that code into somewhere
    # re-usable and call it here and on demand.
    @rx.background
    async def finish_user_create(self, user_id: str):
        with rx.session() as session:
            user = session.get(User, user_id)        
            await self.create_loops_contact_and_send_welcome_email(user)

    def resolve_new_user_tenant(self, user: User, session: Session):
        session.add(user)
        session.commit()
        session.refresh(user)
        tenant = user.lookup_tenant(session)
        if tenant is None:
            tenant = Tenant(domain=user.email_domain, name=user.username + " Org")
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
            member = TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner")
            session.add(member)
            session.commit()
            session.refresh(member)
        user.tenant_id = tenant.id
        session.add(user)
        session.commit()
        session.refresh(user)

    async def create_loops_contact(self, user: User) -> str | None:
        api_key = config.get_global("LOOPS_API_KEY", required=False) or None
        if api_key is None:
            logger.warn("LOOPS_API_KEY not found")
            return
        
        split_name = user.name.split(" ") if user.name else ""
        first_name = split_name[0]
        last_name = " ".join(split_name[1:]) if len(split_name) > 1 else ""
        payload = {
            "email": user.email,
            "firstName": first_name,
            "lastName": last_name,
            "subscribed": True,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post("https://app.loops.so/api/v1/contacts/create", json=payload, headers=headers)

        if response.ok:
            print(f"[Loops] contact created for user {user.id}")
        else:
            logger.warn(f"[Loops] error creating contact: response code {response.status_code} from Loops API")
            if "message" in response.json():
                logger.warn(f"{response.json()['message']}")

        try:
            return response.json()["id"]
        except:
            logger.warn("[Loops] unexpected response format")
            return

    async def send_welcome_email(self, user: User, loops_contact_id: str):
        api_key = config.get_global("LOOPS_API_KEY", required=False) or None
        if api_key is None:
            logger.warn("LOOPS_API_KEY not found")
            return
        
        if not user.email and not loops_contact_id:
            logger.warn("[Loops] welcome email not sent, insufficent parameters provided")
            return

        payload = {
            "eventName": "signup"
        }
        if user.email:
            payload["email"] = user.email
        if loops_contact_id:
            payload["userId"] = loops_contact_id

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post("https://app.loops.so/api/v1/events/send", json=payload, headers=headers)

        if response.ok:
            print(f"[Loops] welcome email sent for user {user.id}")
        else:
            logger.warn(f"[Loops] error sending welcome email: response code {response.status_code} from Loops API")

    
    async def create_loops_contact_and_send_welcome_email(self, user: User):
        loops_contact_id = await self.create_loops_contact(user)
        await self.send_welcome_email(user=user, loops_contact_id=loops_contact_id)

    async def send_pwreset(self):
        with rx.session() as sess:
            user = sess.exec(select(User).where(User.email == self.pwreset_email)).first()
            if user and user.email:
                secret = "reset:" + uuid4().hex
                await pubsub.set(secret, user.id, ttl=60*30)
                link = f"{self.get_server_host}?secret={secret}"
                send_email(user.email, EMAIL_KEYS.PWRESET, {"link":link})
                self.pwreset_message = "Password reset link sent! Check your email."
                self.pwreset_email = ""
            else:
                self.pwreset_message = "Email not found."

    async def reset_password(
            self, 
            form_data: dict
    ) -> AsyncGenerator[rx.event.EventSpec | list[rx.event.EventSpec] | None, None]:
        # The key to this form submit method is that the user must have
        # loaded the pwreset page with "?secret=xx" set so that we found the
        # secret in Redis, and then assigned the secret to our var 'pwreset_secret'.
        # So now we recheck the value in Redis and take user_id to update from there.
        password = form_data['password']
        confirm = form_data['confirm_password']
        if password != confirm:
            self.pwreset_message = "Passwords do not match"
            return
        if len(password) < 8:
            self.pwreset_message = "Passwords must be at least 8 characters"
            return
        
        if self.pwreset_secret:
            user_id = await pubsub.get(self.pwreset_secret)
            with rx.session() as sess:
                await pubsub.delete(self.pwreset_secret)
                user = sess.get(User, user_id)
                if user:
                    user.password_hash = User.hash_password(password)
                    user.enabled = True
                    sess.commit()
                    self.pwreset_message = "Password updated"
                    yield
                    await asyncio.sleep(1.0)
                    self._login(user.id, user.name or "")
                    yield [LoginState.redir(), LoginState.clear_pwreset]
                else:
                    self.pwreset_message = "Account not found"

    @rx.background
    async def clear_pwreset(self):
        await asyncio.sleep(3)
        print("Clearing pwreset secret")
        async with self:
            self.pwreset_secret = ""

    async def pwreset_page_load(self) -> str|None:
        self.pwreset_secret = "" 
        self.pwreset_message = ""
        secret = self.router.page.params.get("secret", "")
        if secret:
            user_id = await pubsub.get(secret)
            if user_id is None:
                self.pwreset_message = "Link expired"
                return None
            else:
                self.pwreset_secret = secret
