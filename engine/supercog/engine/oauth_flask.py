import os
from re import S

from flask import Flask, request, redirect, url_for, session, current_app
from flask_dance.contrib.salesforce import make_salesforce_blueprint, salesforce
from flask_dance.contrib.google import make_google_blueprint, google
from werkzeug.middleware.proxy_fix import ProxyFix

from supercog.shared.services import config, get_public_service_domain

if config.is_dev():
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

oauth_app = Flask(__name__)
oauth_app.wsgi_app = ProxyFix(
    oauth_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

LOGIN_CALLBACK = None # will be set by main.py

## EXPLANATION OF ROUTES
#
# Note that `main` above us anchors the Flask app under '/login' so that can
# be assumed to start every route in here.
#
# 1.
# /login/start_google     - Setup our session and redirect to Google blueprint
# /login/start_salesforce - Setup our session and redirect to Salesforce blueprint
#
# 2.
# /login/google           - Blueprint start route which redirects to Google auth
# /login/salesforce       - Blueprint start route which redirects to Salesforce auth
#
# 3.
# /login/google/authorized - Blueprint return route come back from Google auth
# /login/salesforce/authorized  - Blueprint return route come back from Salesforce auth
#
# 4.
# /login/finish_google     - Our final route - we send auth data to Main and redirect
#                            back to the callers `return_url`
# /login/finish_salesforce - 

# The following is horrible and ugly. When we run behind the nginx proxy then
# it will send the external Host name in the header. We need to match that
# or these Flask routes won't match. The basic problem is trying to run directly
# on the 8001 port or behind nginx.
if not config.is_dev():
    oauth_app.config['SERVER_NAME'] = get_public_service_domain("engine")
# google wants this I guess
oauth_app.config['OAUTHLIB_RELAX_TOKEN_SCOPE']=1

oauth_app.secret_key = config.get_global("GOOGLE_CLIENT_SECRET", required=False) or "??" #any secret would do
blueprint = make_salesforce_blueprint(
    client_id=config.get_global("SALESFORCE_CLIENT_ID", required=False) or "NOTSET_SF_CLIENT_ID",
    client_secret=config.get_global("SALESFORCE_CLIENT_SECRET", required=False) or "NOTSET_SF_CLIENT_SECRET",
    redirect_url="/login/finish_salesforce",
    reprompt_consent=True 
)
blueprint.authorization_url_params["prompt"] = "login"

google_blueprint = make_google_blueprint(
    client_id=config.get_global("GSUITE_CLIENT_ID", required=False) or "NOTSET_GOOGLE_CLIENT_ID",
    client_secret=config.get_global("GSUITE_CLIENT_SECRET", required=False) or "NOTSET_GOOGLE_CLIENT_SECRET",
    scope=(config.get_global("GSUITE_SCOPES", required=False) or "").split(","),
    redirect_url="/login/finish_google",
    offline=True,
    reprompt_consent=True,
)

# We let the root FastAPI app set the /login path
oauth_app.register_blueprint(blueprint, url_prefix="/")
oauth_app.register_blueprint(google_blueprint, url_prefix="/")


def setup_session(args: dict):
    return_url = request.args.get("return_url")
    ut_id = request.args.get("ut_id")
    cred_name = request.args.get("cred_name")

    print("Putting ut_id in session: ", ut_id)
    session["ut_id"] = ut_id
    session["return_url"] = return_url
    session["cred_name"] = cred_name
    session["tool_factory_id"] = request.args.get("tool_factory_id")

def retrieve_session() -> tuple[str, str, str, str]:
    ut_id = session["ut_id"]
    return_url = session["return_url"]
    cred_name = session["cred_name"]
    tool_factory_id = session["tool_factory_id"]

    return ut_id, return_url, cred_name, tool_factory_id

## GOOGLE

# the 'gmailapi' route part is the prefix on the GMailAPITool tool factory
@oauth_app.route("/start_google")
def start_google():
    print("!! IN THE START Google ROUTE", request.args)
    setup_session(request.args)

    redir = url_for("google.login")
    print("Returning redirect to ", redir)
    return redirect(redir)

@oauth_app.route("/finish_google")
def after_google_login():
    # 'google' object should have our tokens now
    print("!! In the after_login route")
    ut_id, return_url, cred_name, tool_factory_id = retrieve_session()

    if LOGIN_CALLBACK:
        LOGIN_CALLBACK(ut_id, cred_name, tool_factory_id, google, {})
        print("Returning redirect to: ", return_url)
        return redirect(return_url)
    return ""

## SALESFORCE

@oauth_app.route("/start_salesforce")
def start_salesforce():
    global blueprint
    print("!! IN THE START Salesforce ROUTE", request.args)

    customhost = request.args.get("customhost")
    # 'customhost' is only for Salesforce
    update_salesforce_blueprint(customhost)    
    
    print(f"\n\nAfter Salesforce setup to host: {customhost}, blueprint dict is: ", blueprint.__dict__)

    setup_session(request.args)
    #oauth_app.register_blueprint(blueprint, url_prefix="/")

    redir = url_for("salesforce.login")
    print("Returning redirect to ", redir)
    return redirect(redir)

def update_salesforce_blueprint(customhost):
    global blueprint

    if customhost:
        newhost = customhost
        if not customhost.startswith("https://"):
            newhost = "https://" + customhost
        
        print("Newhost ", newhost)
        match = "https://login.salesforce.com" 
        if 'sandbox' in customhost:
            newhost = "https://test.salesforce.com" 

        for attr, val in blueprint.__dict__.items():
            if val and isinstance(val, str) and val.startswith(match):
                val = val.replace(match, newhost)
                print("Setting ", attr, " to ", val)
                setattr(blueprint, attr, val)

        blueprint.base_url = newhost
    else:
        newhost = "https://login.salesforce.com" 
        match = "https://test.salesforce.com" 
        for attr, val in blueprint.__dict__.items():
            if val and isinstance(val, str) and val.startswith(match):
                val = val.replace(match, newhost)
                print("Setting ", attr, " to ", val)
                setattr(blueprint, attr, val)
        blueprint.base_url = newhost


@oauth_app.route("/finish_salesforce")
def after_saleforce_login():
    # 'salesforce' object should have our tokens now
    print("!! In the after_login route")
    resp = salesforce.get("/services/oauth2/userinfo") #/user
    print(resp.text)
    print("User: ", resp.json())

    ut_id, return_url, cred_name, tool_factory_id = retrieve_session()

    if LOGIN_CALLBACK:
        LOGIN_CALLBACK(ut_id, cred_name, tool_factory_id, salesforce, resp.json())
        print("Returning redirect to: ", return_url)
        return redirect(return_url)
    return "You are @{login} on Salesforce".format(login=resp.json()["name"])

def debug_routes():
    for rule in oauth_app.url_map.iter_rules():
        print(rule)


