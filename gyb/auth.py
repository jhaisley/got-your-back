#!/usr/bin/env python3
#
# Got Your Back - Authentication Functions
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import re
import datetime
import json
import multiprocessing
import os
import sys
import threading
import time
import webbrowser
import wsgiref.simple_server
import wsgiref.util
from urllib.parse import parse_qs, urlencode, urlparse

import google.oauth2.credentials
import google.oauth2.id_token
import google.oauth2.service_account
import google_auth_httplib2
import google_auth_oauthlib.flow

from .utils import (
    _createHttpObj,
    _localhost_to_ip,
    getGYBVersion,
    readFile,
    shorten_url,
    systemErrorExit,
    writeFile,
)


def getValidOauth2TxtCredentials(force_refresh=False):
    """Gets OAuth2 credentials which are guaranteed to be fresh and valid."""
    credentials = getOauth2TxtStorageCredentials()
    if credentials is None or not credentials.valid:
        requestOAuthAccess()
        credentials = getOauth2TxtStorageCredentials()
    if force_refresh:
        credentials.refresh(google_auth_httplib2.Request(_createHttpObj()))
    return credentials


def getOauth2TxtStorageCredentials():
    from . import options

    auth_as = options.use_admin if options.use_admin else options.email
    cfgFile = os.path.join(options.config_folder, "%s.cfg" % auth_as)
    oauth_string = readFile(cfgFile, continueOnError=True, displayError=False)
    if not oauth_string:
        return
    oauth_data = json.loads(oauth_string)
    oauth_data["type"] = "authorized_user"
    if os.environ.get("GOOGLE_API_CLIENT_CERTIFICATE") and os.environ.get(
        "GOOGLE_API_CLIENT_PRIVATE_KEY"
    ):
        oauth_data["token_uri"] = "https://oauth2.mtls.googleapis.com/token"
    else:
        oauth_data["token_uri"] = "https://oauth2.googleapis.com/token"
    google.oauth2.credentials._GOOGLE_OAUTH2_TOKEN_ENDPOINT = oauth_data["token_uri"]
    creds = google.oauth2.credentials.Credentials.from_authorized_user_info(oauth_data)
    creds.token = oauth_data.get("token", oauth_data.get("auth_token", ""))
    creds._id_token = oauth_data.get("id_token_jwt", oauth_data.get("id_token", None))
    token_expiry = oauth_data.get("token_expiry", "1970-01-01T00:00:01Z")
    creds.expiry = datetime.datetime.strptime(token_expiry, "%Y-%m-%dT%H:%M:%SZ")
    return creds


def getOAuthClientIDAndSecret():
    """Retrieves the OAuth client ID and client secret from JSON."""
    from . import options

    MISSING_CLIENT_SECRETS_MESSAGE = """Please configure a project

To make GYB run you will need to populate the client_secrets.json file. Try
running:

%s --action create-project --email %s

""" % (
        sys.argv[0],
        options.email,
    )
    filename = os.path.join(options.config_folder, "client_secrets.json")
    cs_data = readFile(filename, continueOnError=True, displayError=True)
    if not cs_data:
        systemErrorExit(14, MISSING_CLIENT_SECRETS_MESSAGE)
    try:
        cs_json = json.loads(cs_data)
        client_id = cs_json["installed"]["client_id"]
        # chop off .apps.googleusercontent.com suffix as it's not needed
        # and we need to keep things short for the Auth URL.
        client_id = re.sub(r"\.apps\.googleusercontent\.com$", "", client_id)
        client_secret = cs_json["installed"]["client_secret"]
    except (ValueError, IndexError, KeyError):
        systemErrorExit(
            3,
            "the format of your client secrets file:\\n\\n%s\\n\\n"
            "is incorrect. Please recreate the file." % filename,
        )
    return (client_id, client_secret)


def requestOAuthAccess():
    from . import options

    auth_as = options.use_admin if options.use_admin else options.email
    credentials = getOauth2TxtStorageCredentials()
    if credentials and credentials.valid:
        return
    client_id, client_secret = getOAuthClientIDAndSecret()
    possible_scopes = [
        "https://www.googleapis.com/auth/gmail.modify",  # Gmail modify
        "https://www.googleapis.com/auth/gmail.readonly",  # Gmail readonly
        "https://www.googleapis.com/auth/gmail.insert https://www.googleapis.com/auth/gmail.labels",  # insert and labels
        "https://mail.google.com/",  # Gmail Full Access
        "",  # No Gmail
        "https://www.googleapis.com/auth/apps.groups.migration",  # Groups Archive Restore
        "https://www.googleapis.com/auth/drive.appdata",
    ]  # Drive app config (used for quota)
    selected_scopes = [" ", " ", " ", "*", " ", "*", "*"]
    menu = """Select the actions you wish GYB to be able to perform for %s

[%s]  0)  Gmail Backup And Restore - read/write mailbox access
[%s]  1)  Gmail Backup Only - read-only mailbox access
[%s]  2)  Gmail Restore Only - write-only mailbox access and label management
[%s]  3)  Gmail Full Access - read/write mailbox access and message management
[%s]  4)  No Gmail access
[%s]  5)  Groups Restore - write to Google Groups
[%s]  6)  Storage Quota - Drive app config scope used for --action quota

""" % (
        auth_as,
        selected_scopes[0],
        selected_scopes[1],
        selected_scopes[2],
        selected_scopes[3],
        selected_scopes[4],
        selected_scopes[5],
        selected_scopes[6],
    )

    scopes = []
    for i in range(0, len(selected_scopes)):
        if selected_scopes[i] == "*":
            scopes.append(possible_scopes[i])
    credentials = _run_oauth_flow(
        client_id, client_secret, scopes, access_type="offline", login_hint=auth_as
    )
    writeCredentials(credentials)


def writeCredentials(creds):
    from . import options

    auth_as = options.use_admin if options.use_admin else options.email
    cfgFile = os.path.join(options.config_folder, "%s.cfg" % auth_as)
    data = (
        '{"token": "%s", "refresh_token": "%s", "id_token_jwt": "%s", "token_expiry": "%s", "client_id": "%s", "client_secret": "%s"}'
        % (
            creds.token,
            creds.refresh_token,
            getattr(creds, "_id_token", ""),
            (
                creds.expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
                if creds.expiry
                else "1970-01-01T00:00:01Z"
            ),
            creds.client_id,
            creds.client_secret,
        )
    )
    writeFile(cfgFile, data)


def _decodeIdToken(credentials=None):
    credentials = (
        credentials if credentials is not None else getValidOauth2TxtCredentials()
    )
    httpc = google_auth_httplib2.Request(_createHttpObj())
    return google.oauth2.id_token.verify_oauth2_token(
        credentials.id_token, httpc, clock_skew_in_seconds=10
    )


def _getValueFromOAuth(field, credentials=None):
    id_token = _decodeIdToken(credentials)
    return id_token.get(field, "Unknown")


def doesTokenMatchEmail():
    from . import options
    from .google_api import buildGAPIObject, callGAPI

    auth_as = options.use_admin if options.use_admin else options.email
    oa2 = buildGAPIObject("oauth2")
    user_info = callGAPI(oa2.userinfo(), "get", fields="email")
    if user_info["email"].lower() == auth_as.lower():
        return True
    print(
        "Error: you did not authorize the OAuth token in the browser with the \
%s Google Account. Please make sure you are logged in to the correct account \
when authorizing the token in the browser."
        % auth_as
    )
    cfgFile = os.path.join(options.config_folder, "%s.cfg" % auth_as)
    os.remove(cfgFile)
    return False


def getValidateLoginHint(login_hint):
    import ipaddress

    try:
        ipaddress.ip_address(login_hint)
        return None
    except ValueError:
        pass
    if login_hint.find("@") == -1:
        return None
    return login_hint


class ShortURLFlow(google_auth_oauthlib.flow.InstalledAppFlow):
    def authorization_url(self, **kwargs):
        auth_url, state = super().authorization_url(**kwargs)
        shortened_url = shorten_url(auth_url)
        if shortened_url != auth_url:
            print("Go to the following link in a browser on this or another machine:")
            print("")
            print("  %s" % shortened_url)
            print("")
            print(
                "If you use this machine's browser, click the Browser Auth button on the page."
            )
            print(
                "If you use a different machine's browser, click the Console Auth button on the page."
            )
        else:
            print("Go to the following link in your browser:")
            print("")
            print("  %s" % shortened_url)
            print("")
        return auth_url, state

    def run_dual(
        self,
        use_console_flow,
        authorization_prompt_message="",
        console_prompt_message="",
        web_success_message="",
        open_browser=True,
        redirect_uri_trailing_slash=True,
        **kwargs,
    ):
        if sys.platform == "darwin":
            multiprocessing.set_start_method("fork")
        mgr = multiprocessing.Manager()
        d = mgr.dict()
        d["trailing_slash"] = redirect_uri_trailing_slash
        d["open_browser"] = use_console_flow
        http_client = multiprocessing.Process(target=_wait_for_http_client, args=(d,))
        user_input = multiprocessing.Process(target=_wait_for_user_input, args=(d,))
        http_client.start()
        # we need to wait until web server starts on avail port
        # so we know redirect_uri to use
        while "redirect_uri" not in d:
            time.sleep(0.1)
        self.redirect_uri = d["redirect_uri"]
        d["auth_url"], _ = self.authorization_url(**kwargs)
        user_input.start()
        # we need to wait until auth_code is provided by one of the methods
        while "auth_code" not in d:
            time.sleep(0.1)
        http_client.terminate()
        user_input.terminate()
        self.fetch_token(code=d["auth_code"])


def _wait_for_http_client(d):
    class AuthHandler(wsgiref.simple_server.WSGIRequestHandler):
        def log_message(self, format, *args):
            pass

    class AuthApplication:
        def __call__(self, environ, start_response):
            query_string = environ.get("QUERY_STRING", "")
            if not query_string:
                status = "200 OK"
                response_headers = [("Content-type", "text/html")]
                start_response(status, response_headers)
                return [
                    b"""<!DOCTYPE html>
<html>
<head>
    <title>GYB Authorization</title>
</head>
<body>
    <h2>GYB Authorization</h2>
    <p>Please choose your authentication method:</p>
    <br>
    <p><a href="#" onclick="window.open(auth_url, '_blank'); return false;">
    <button style="font-size:16px; padding:10px;">Browser Auth (use this browser)</button></a></p>
    <br>
    <p><a href="#" onclick="showConsoleAuth(); return false;">
    <button style="font-size:16px; padding:10px;">Console Auth (use different browser/machine)</button></a></p>
    <div id="console-auth" style="display:none;">
        <br>
        <p>On your other machine/browser, go to:</p>
        <p><strong id="auth-url-display"></strong></p>
        <br>
        <p>After you authorize, enter the authorization code below:</p>
        <form onsubmit="submitCode(); return false;">
            <input type="text" id="auth-code" placeholder="Enter authorization code" style="width:300px; font-size:14px; padding:5px;">
            <br><br>
            <button type="submit" style="font-size:16px; padding:10px;">Submit</button>
        </form>
    </div>
    <script>
        var auth_url = '%s';
        
        function showConsoleAuth() {
            document.getElementById('console-auth').style.display = 'block';
            document.getElementById('auth-url-display').textContent = auth_url;
        }
        
        function submitCode() {
            var code = document.getElementById('auth-code').value;
            if (code) {
                fetch('/?code=' + encodeURIComponent(code))
                    .then(() => {
                        document.body.innerHTML = '<h2>Authorization successful!</h2><p>You can close this window.</p>';
                    });
            }
        }
    </script>
</body>
</html>"""
                    % d["auth_url"]
                ]
            parsed = parse_qs(query_string)
            if "code" in parsed:
                d["auth_code"] = parsed["code"][0]
                status = "200 OK"
                response_headers = [("Content-type", "text/html")]
                start_response(status, response_headers)
                return [
                    b"<h2>Authorization successful!</h2><p>You can close this window.</p>"
                ]
            else:
                status = "400 Bad Request"
                response_headers = [("Content-type", "text/html")]
                start_response(status, response_headers)
                return [b"Invalid request"]

    app = AuthApplication()
    httpd = wsgiref.simple_server.make_server(
        _localhost_to_ip(), 0, app, handler_class=AuthHandler
    )
    port = httpd.server_port
    redirect_uri = f"http://{_localhost_to_ip()}:{port}/"
    if d["trailing_slash"] and not redirect_uri.endswith("/"):
        redirect_uri += "/"
    d["redirect_uri"] = redirect_uri
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _wait_for_user_input(d):
    while "auth_url" not in d:
        time.sleep(0.1)
    time.sleep(1)  # wait for URL to be displayed
    if d["open_browser"]:
        try:
            webbrowser.open(d["auth_url"])
            time.sleep(1)
        except webbrowser.Error:
            pass
    print("Enter verification code: ", end="")
    sys.stdout.flush()
    auth_code = input().strip()
    if auth_code:
        d["auth_code"] = auth_code


def _run_oauth_flow(client_id, client_secret, scopes, access_type, login_hint=None):
    token_uri = "https://oauth2.googleapis.com/token"
    if os.environ.get("GOOGLE_API_CLIENT_CERTIFICATE") and os.environ.get(
        "GOOGLE_API_CLIENT_PRIVATE_KEY"
    ):
        token_uri = "https://oauth2.mtls.googleapis.com/token"
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": token_uri,
        }
    }
    flow = ShortURLFlow.from_client_config(
        client_config, scopes, autogenerate_code_verifier=True
    )
    kwargs = {"access_type": access_type}
    if login_hint:
        kwargs["login_hint"] = login_hint
    # Needs to be set so oauthlib doesn't puke when Google changes our scopes
    import os

    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "true"
    flow.run_dual(use_console_flow=True, **kwargs)
    return flow.credentials


def getSvcAcctCredentials(scopes, act_as):
    from . import options

    keyFile = os.path.join(options.config_folder, options.service_account)
    with open(keyFile, "r") as f:
        key_data = f.read()
    key_data = json.loads(key_data)
    credentials = google.oauth2.service_account.Credentials.from_service_account_info(
        key_data, scopes=scopes
    )
    if act_as:
        credentials = credentials.with_subject(act_as)
    return credentials


def getSvcAccountClientId():
    from . import options

    keyFile = os.path.join(options.config_folder, options.service_account)
    with open(keyFile, "r") as f:
        key_data = f.read()
    key_data = json.loads(key_data)
    return key_data["client_id"]


