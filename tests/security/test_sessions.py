from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
    get_user_model,
    _get_backends,
)


from channels.db import database_sync_to_async
from channels.security.sessions import SessionCheckAsyncWebsocketConsumer
from channels.sessions import SessionMiddlewareStack
from channels.testing import WebsocketCommunicator


@pytest.fixture
def user():
    return get_user_model().objects.create(username="bob", email="bob@example.com")


@pytest.fixture
def logged_session(user):
    SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
    session = SessionStore()
    session.create()
    session_auth_hash = ""
    if hasattr(user, "get_session_auth_hash"):
        session_auth_hash = user.get_session_auth_hash()
    try:
        backend = user.backend
    except AttributeError:
        backends = _get_backends(return_tuples=True)
        if len(backends) == 1:
            _, backend = backends[0]
        else:
            raise ValueError(
                "You have multiple authentication backends configured and "
                "therefore must provide the `backend` "
                "argument or set the `backend` attribute on the user."
            )
    session[SESSION_KEY] = user._meta.pk.value_to_string(user)
    session[BACKEND_SESSION_KEY] = backend
    session[HASH_SESSION_KEY] = session_auth_hash
    return session


@pytest.fixture
def ws_check_soon(settings):
    settings.CHANNELS_WS_SESSION_CHECK_INTERVAL = 2


@database_sync_to_async
def flush_session(session):
    session.flush()
    assert SESSION_KEY not in session
    assert BACKEND_SESSION_KEY not in session
    assert HASH_SESSION_KEY not in session


@database_sync_to_async
def change_user_password(user):
    user.set_password('other')
    user.save()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_check_session_logut(logged_session, ws_check_soon):
    """
    Tests a close frame is sent to user after session is flushed
    """
    app = SessionMiddlewareStack(SessionCheckAsyncWebsocketConsumer())
    communicator = WebsocketCommunicator(app, "/")
    # add session and connect
    communicator.scope["session"] = logged_session
    connected, _ = await communicator.connect()
    assert connected
    # destroy session
    await flush_session(logged_session)
    await communicator.receive_disconnect(timeout=3)
    # Close out
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_check_session_password_change(logged_session, user, ws_check_soon):
    """
    Tests a close frame is sent to user after a password change
    """
    # TODO this may have a "skipIf" or we can just assume this will always be tested against a model which
    # implements get_session_auth_hash
    assert hasattr(user, "get_session_auth_hash")
    assert logged_session[HASH_SESSION_KEY] == user.get_session_auth_hash()
    app = SessionMiddlewareStack(SessionCheckAsyncWebsocketConsumer())
    communicator = WebsocketCommunicator(app, "/")
    # add session and connect
    communicator.scope["session"] = logged_session
    connected, _ = await communicator.connect()
    assert connected
    # changing password invalidates session auth hash
    await change_user_password(user)
    assert logged_session[HASH_SESSION_KEY] != user.get_session_auth_hash()
    await communicator.receive_disconnect(timeout=3)
    # Close out
    await communicator.disconnect()




