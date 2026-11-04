"""Windows integrated authentication (SSPI) using only the Python standard library.

Talks to the Windows Security Support Provider Interface (``Secur32.dll``) through ``ctypes`` to
obtain Negotiate/NTLM tokens. By default it uses the **logged-on user's** credentials (no password
is read or stored). Optionally it can use **explicit credentials** typed by the operator
(domain/user/password) — held in memory only, never written to disk or logs — for the case where
the Windows session account is not the one authorized in FactoryLogix.

* No external package is installed (no ``pip``), no administrator rights.
* Works only on Windows. ``sspi_available()`` is ``False`` elsewhere (e.g. Linux CI), so the rest of
  the app falls back to anonymous requests and the unit tests do not need SSPI.

Only the token handshake lives here; the HTTP side is in ``odata_client`` so it reuses the same
bounded-read, redirect-block and size-limit protections as the anonymous transport.
"""
from __future__ import annotations

import sys

# SSPI return codes.
SEC_E_OK = 0x00000000
SEC_I_CONTINUE_NEEDED = 0x00090312
SEC_I_COMPLETE_NEEDED = 0x00090313
SEC_I_COMPLETE_AND_CONTINUE = 0x00090314

_SECPKG_CRED_OUTBOUND = 0x00000002
_SECURITY_NATIVE_DREP = 0x00000010
_SECBUFFER_TOKEN = 0x00000002
_SECBUFFER_VERSION = 0x00000000
_ISC_REQ_ALLOCATE_MEMORY = 0x00000100
_ISC_REQ_CONNECTION = 0x00000800
_ISC_FLAGS = _ISC_REQ_ALLOCATE_MEMORY | _ISC_REQ_CONNECTION
_SEC_WINNT_AUTH_IDENTITY_UNICODE = 0x00000002


class SspiError(Exception):
    """An SSPI call failed. ``status`` holds the raw SECURITY_STATUS when available."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class WindowsCredentials:
    """Optional explicit credentials, kept in memory only (never persisted or logged)."""

    def __init__(self) -> None:
        self.user: str | None = None
        self.domain: str | None = None
        self._password: str | None = None

    def set(self, user: str, password: str, domain: str | None = None) -> None:
        user = (user or "").strip()
        if not user or password is None:
            raise ValueError("Usuario y contraseña son obligatorios.")
        if "\\" in user and not domain:  # accept DOMAIN\user
            domain, user = user.split("\\", 1)
        self.user, self.domain, self._password = user, (domain or "").strip() or None, password

    def clear(self) -> None:
        self.user = self.domain = self._password = None

    @property
    def present(self) -> bool:
        return bool(self.user and self._password is not None)

    @property
    def display(self) -> str:
        if not self.present:
            return "Sesión de Windows (usuario actual)"
        return f"{self.domain + chr(92) if self.domain else ''}{self.user}"

    def identity(self) -> tuple[str, str, str] | None:
        """(user, password, domain) for SSPI, or None to use the logged-on user."""
        return (self.user, self._password, self.domain or "") if self.present else None


def sspi_available() -> bool:
    """True only on Windows with a usable Secur32.dll."""
    if sys.platform != "win32":
        return False
    try:  # pragma: no cover - exercised only on Windows
        import ctypes

        ctypes.WinDLL("Secur32.dll")
        return True
    except Exception:  # noqa: BLE001
        return False


if sys.platform == "win32":  # pragma: no cover - requires Windows SSPI
    import ctypes
    from ctypes import POINTER, byref, c_ulong, c_void_p, c_wchar_p

    _secur32 = ctypes.WinDLL("Secur32.dll")

    class _SecurityInteger(ctypes.Structure):
        _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]

    class _SecHandle(ctypes.Structure):
        _fields_ = [("lower", c_void_p), ("upper", c_void_p)]

    class _SecBuffer(ctypes.Structure):
        _fields_ = [("cbBuffer", c_ulong), ("BufferType", c_ulong), ("pvBuffer", c_void_p)]

    class _SecBufferDesc(ctypes.Structure):
        _fields_ = [("ulVersion", c_ulong), ("cBuffers", c_ulong), ("pBuffers", POINTER(_SecBuffer))]

    class _SecWinntAuthIdentity(ctypes.Structure):
        _fields_ = [("User", c_wchar_p), ("UserLength", c_ulong), ("Domain", c_wchar_p),
                    ("DomainLength", c_ulong), ("Password", c_wchar_p), ("PasswordLength", c_ulong),
                    ("Flags", c_ulong)]

    _PSecHandle = POINTER(_SecHandle)
    _PSecBufferDesc = POINTER(_SecBufferDesc)
    _PTimeStamp = POINTER(_SecurityInteger)
    _LONG = ctypes.c_long

    # Declaring argtypes/restype is essential on 64-bit: otherwise pointers default to C int and
    # overflow ("int too long to convert"), which is exactly the bug this replaces.
    _AcquireCredentialsHandle = _secur32.AcquireCredentialsHandleW
    _AcquireCredentialsHandle.restype = _LONG
    _AcquireCredentialsHandle.argtypes = [c_wchar_p, c_wchar_p, c_ulong, c_void_p, c_void_p,
                                          c_void_p, c_void_p, _PSecHandle, _PTimeStamp]

    _InitializeSecurityContext = _secur32.InitializeSecurityContextW
    _InitializeSecurityContext.restype = _LONG
    _InitializeSecurityContext.argtypes = [_PSecHandle, _PSecHandle, c_wchar_p, c_ulong, c_ulong,
                                           c_ulong, _PSecBufferDesc, c_ulong, _PSecHandle,
                                           _PSecBufferDesc, POINTER(c_ulong), _PTimeStamp]

    _FreeContextBuffer = _secur32.FreeContextBuffer
    _FreeContextBuffer.restype = _LONG
    _FreeContextBuffer.argtypes = [c_void_p]

    _DeleteSecurityContext = _secur32.DeleteSecurityContext
    _DeleteSecurityContext.restype = _LONG
    _DeleteSecurityContext.argtypes = [_PSecHandle]

    _FreeCredentialsHandle = _secur32.FreeCredentialsHandle
    _FreeCredentialsHandle.restype = _LONG
    _FreeCredentialsHandle.argtypes = [_PSecHandle]

    class _WindowsSspiClient:
        """One authentication handshake against a single target."""

        def __init__(self, package: str, target_spn: str,
                     identity: tuple[str, str, str] | None = None) -> None:
            self.package = package
            self.target_spn = target_spn
            self.complete = False
            self._cred = _SecHandle()
            self._ctx = _SecHandle()
            self._have_ctx = False
            self._auth = None
            auth_ptr = None
            if identity is not None:
                user, password, domain = identity
                self._auth = _SecWinntAuthIdentity(
                    User=user, UserLength=len(user), Domain=domain, DomainLength=len(domain),
                    Password=password, PasswordLength=len(password), Flags=_SEC_WINNT_AUTH_IDENTITY_UNICODE)
                auth_ptr = ctypes.cast(ctypes.pointer(self._auth), c_void_p)
            expiry = _SecurityInteger()
            status = _AcquireCredentialsHandle(None, package, _SECPKG_CRED_OUTBOUND,
                                               None, auth_ptr, None, None, byref(self._cred), byref(expiry))
            if status < 0:
                raise SspiError(f"AcquireCredentialsHandle({package}) failed", status)

        def _step(self, challenge: bytes | None) -> bytes:
            out_buf = _SecBuffer(0, _SECBUFFER_TOKEN, None)
            out_desc = _SecBufferDesc(_SECBUFFER_VERSION, 1, ctypes.pointer(out_buf))
            in_desc_ptr = None
            in_storage = None
            in_buf = None
            if challenge:
                in_storage = ctypes.create_string_buffer(bytes(challenge), len(challenge))
                in_buf = _SecBuffer(len(challenge), _SECBUFFER_TOKEN, ctypes.cast(in_storage, c_void_p))
                in_desc = _SecBufferDesc(_SECBUFFER_VERSION, 1, ctypes.pointer(in_buf))
                in_desc_ptr = ctypes.pointer(in_desc)
            attrs = c_ulong(0)
            expiry = _SecurityInteger()
            ctx_in = byref(self._ctx) if self._have_ctx else None
            status = _InitializeSecurityContext(
                byref(self._cred), ctx_in, self.target_spn, _ISC_FLAGS, 0, _SECURITY_NATIVE_DREP,
                in_desc_ptr, 0, byref(self._ctx), byref(out_desc), byref(attrs), byref(expiry))
            _ = (in_storage, in_buf)  # keep input buffers alive until the call returns
            if status < 0:
                raise SspiError("InitializeSecurityContext failed", status)
            self._have_ctx = True
            if status in (SEC_E_OK, SEC_I_COMPLETE_NEEDED):
                self.complete = True
            token = b""
            if out_buf.pvBuffer and out_buf.cbBuffer:
                token = ctypes.string_at(out_buf.pvBuffer, out_buf.cbBuffer)
                _FreeContextBuffer(out_buf.pvBuffer)
            return token

        def first_token(self) -> bytes:
            return self._step(None)

        def next_token(self, challenge: bytes) -> bytes:
            return self._step(challenge)

        def close(self) -> None:
            if self._have_ctx:
                _DeleteSecurityContext(byref(self._ctx))
                self._have_ctx = False
            _FreeCredentialsHandle(byref(self._cred))
            self._auth = None  # drop the in-memory password reference


def make_client(package: str, target_spn: str, identity: tuple[str, str, str] | None = None):
    """Create an SSPI handshake client. ``identity`` None = logged-on user; else (user, password, domain).

    Raises ``SspiError`` if SSPI is not available on this platform.
    """
    if sys.platform != "win32":
        raise SspiError("SSPI is only available on Windows")
    return _WindowsSspiClient(package, target_spn, identity)  # pragma: no cover - Windows only
